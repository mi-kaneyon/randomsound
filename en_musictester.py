import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re
import random
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage
import numpy as np

########################
# 1. Scales (Music Moods)
########################
SCALE_OPTIONS = {
    "Rock (Minor Pentatonic)":       [0, 3, 5, 7, 10, 12],
    "Blues (Blues Scale)":           [0, 3, 5, 6, 7, 10, 12],
    "Metal (Phrygian Dominant)":     [0, 1, 4, 5, 7, 8, 10, 12],
    "Ballad (Major Scale)":          [0, 2, 4, 5, 7, 9, 11, 12],
    "Classical (Harmonic Minor)":    [0, 2, 3, 5, 7, 8, 11, 12],
}

########################
# 2. Key (Base note)
########################
KEY_OPTIONS = {
    "Low (C3)": 60,
    "Normal (D3)": 62,
    "High (E3)": 64,
}

####################################
# 3. Drum patterns & Markov chain
####################################
DRUM_PATTERN_A = [
    ("K", 1), ("H", 2), ("H", 3), ("H", 4), 
    ("S", 5), ("H", 6), ("H", 7), ("H", 8), 
    ("K", 9), ("H",10), ("H",11), ("H",12), 
    ("S",13), ("H",14), ("H",15), ("H",16),
]
DRUM_PATTERN_B = [
    ("K", 1), ("H", 2), ("H", 3), ("H", 4), 
    ("S", 5), ("H", 6), ("K", 7), ("H", 8), 
    ("K", 9), ("H",10), ("H",11), ("H",12), 
    ("S",13), ("H",14), ("K",15), ("H",16),
]
DRUM_PATTERN_C = [
    ("K", 1), ("H", 2), ("H", 3), ("H", 4),
    ("S", 5), ("H", 6), ("S", 7), ("H", 8),
    ("K", 9), ("K",10), ("S",11), ("S",12),
    ("K",13), ("H",14), ("S",15), ("H",16),
]

DRUM_NOTE_MAP = {
    "K": 36,  # Kick
    "S": 38,  # Snare
    "H": 42,  # Hi-Hat(Closed)
}

DRUM_MARKOV = {
    "A": [("A", 0.4), ("B", 0.4), ("C", 0.2)],
    "B": [("A", 0.3), ("B", 0.2), ("C", 0.5)],
    "C": [("A", 0.6), ("B", 0.4)]
}

def get_drums_pattern_map():
    return {
        "A": DRUM_PATTERN_A,
        "B": DRUM_PATTERN_B,
        "C": DRUM_PATTERN_C
    }

def choose_next_pattern(current_id):
    """Choose the next drum pattern ID using Markov chain."""
    if current_id not in DRUM_MARKOV:
        return None
    choices = DRUM_MARKOV[current_id]
    r = random.random()
    cumul = 0
    for pattern_id, prob in choices:
        cumul += prob
        if r < cumul:
            return pattern_id
    return None

################################
# 4. Drum generation to match melody duration
################################
def generate_drum_to_fit_time(drum_track, total_melody_ticks, channel=9):
    """
    Generate drum patterns until reaching 'total_melody_ticks',
    so that drums end simultaneously with the melody.
    """
    measure_ticks = 1920  # 1 measure = 16 steps * 120 ticks
    current_time = 0

    pattern_map = get_drums_pattern_map()
    current_pattern_id = random.choice(list(pattern_map.keys()))

    while current_time < total_melody_ticks:
        if not current_pattern_id:
            current_pattern_id = random.choice(list(pattern_map.keys()))

        pattern = pattern_map[current_pattern_id]
        leftover = total_melody_ticks - current_time

        if leftover <= 0:
            break

        if leftover >= measure_ticks:
            # Enough time for a full measure
            write_drum_measure(drum_track, pattern, measure_ticks, channel)
            current_time += measure_ticks
        else:
            # Only partial measure left
            write_drum_partial_measure(drum_track, pattern, leftover, channel)
            current_time += leftover
            break

        next_pattern_id = choose_next_pattern(current_pattern_id)
        current_pattern_id = next_pattern_id

def write_drum_measure(drum_track, pattern, measure_ticks, channel=9):
    """
    Write a full measure (16 steps). 
    step_tick = measure_ticks / 16 = 120 by default.
    """
    step_tick = measure_ticks // 16
    accum_time = 0  # to calculate delta_time
    sorted_pattern = sorted(pattern, key=lambda x: x[1])

    for (drum_key, step) in sorted_pattern:
        event_tick = (step - 1) * step_tick
        delta_time = event_tick - accum_time
        accum_time = event_tick

        if drum_key in DRUM_NOTE_MAP:
            note_num = DRUM_NOTE_MAP[drum_key]
            velocity = random.randint(70, 100)
            # Note ON
            drum_track.append(Message('note_on', note=note_num, velocity=velocity, 
                                      time=delta_time, channel=channel))
            # Note OFF after 50 ticks
            drum_track.append(Message('note_off', note=note_num, velocity=0,
                                      time=50, channel=channel))
            accum_time += 50

    # Move to the end of the measure
    remainder = measure_ticks - accum_time
    if remainder < 0:
        remainder = 0
    if remainder > 0:
        # Dummy event to advance time
        drum_track.append(Message('note_on', note=36, velocity=0, 
                                  time=remainder, channel=channel))

def write_drum_partial_measure(drum_track, pattern, leftover_ticks, channel=9):
    """
    Generate a partial measure if leftover_ticks < measure_ticks.
    """
    step_tick = 120  # Usually measure_ticks/16
    accum_time = 0
    sorted_pattern = sorted(pattern, key=lambda x: x[1])

    for (drum_key, step) in sorted_pattern:
        event_tick = (step - 1) * step_tick
        if event_tick > leftover_ticks:
            break
        delta_time = event_tick - accum_time
        accum_time = event_tick

        if drum_key in DRUM_NOTE_MAP:
            note_num = DRUM_NOTE_MAP[drum_key]
            velocity = random.randint(70, 100)
            # Note ON
            drum_track.append(Message('note_on', note=note_num, velocity=velocity,
                                      time=delta_time, channel=channel))
            # Note OFF
            off_time = 50
            if event_tick + off_time > leftover_ticks:
                off_time = leftover_ticks - event_tick
                if off_time < 0:
                    off_time = 0
            drum_track.append(Message('note_off', note=note_num, velocity=0,
                                      time=off_time, channel=channel))
            accum_time += off_time

    remainder = leftover_ticks - accum_time
    if remainder > 0:
        drum_track.append(Message('note_on', note=36, velocity=0, 
                                  time=remainder, channel=channel))

############################################
# 5. Main Tkinter App (Melody & Drums end at the same time)
############################################
class TextToMidiSyncApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Text-based Melody and Drum Sync - MIDI Generator")
        self.geometry("700x500")

        # Main frame
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Text input
        lbl_text = tk.Label(main_frame, text="● Input Text (Generate melody from words):")
        lbl_text.pack(anchor="w")
        self.text_area = tk.Text(main_frame, wrap="word", height=8)
        self.text_area.pack(fill=tk.BOTH, expand=True)

        # Scale (music mood)
        lbl_scale = tk.Label(main_frame, text="● Select Music Scale / Mood:")
        lbl_scale.pack(anchor="w", pady=(10,0))
        self.scale_var = tk.StringVar(value=list(SCALE_OPTIONS.keys())[0])
        self.cmb_scale = ttk.Combobox(main_frame, textvariable=self.scale_var,
                                      values=list(SCALE_OPTIONS.keys()), state="readonly")
        self.cmb_scale.pack(fill=tk.X)

        # Key (pitch)
        lbl_key = tk.Label(main_frame, text="● Select Key (pitch):")
        lbl_key.pack(anchor="w", pady=(10,0))
        self.key_var = tk.StringVar(value=list(KEY_OPTIONS.keys())[0])
        self.cmb_key = ttk.Combobox(main_frame, textvariable=self.key_var,
                                    values=list(KEY_OPTIONS.keys()), state="readonly")
        self.cmb_key.pack(fill=tk.X)

        # BPM
        lbl_bpm = tk.Label(main_frame, text="● Tempo (BPM):")
        lbl_bpm.pack(anchor="w", pady=(10,0))
        self.bpm_var = tk.IntVar(value=120)
        self.scl_bpm = tk.Scale(main_frame, from_=60, to=200, orient=tk.HORIZONTAL,
                                variable=self.bpm_var)
        self.scl_bpm.pack(fill=tk.X)

        # Reverb
        lbl_reverb = tk.Label(main_frame, text="● Reverb (CC#91):")
        lbl_reverb.pack(anchor="w", pady=(10,0))
        self.reverb_var = tk.IntVar(value=40)
        self.scl_reverb = tk.Scale(main_frame, from_=0, to=127, orient=tk.HORIZONTAL,
                                   variable=self.reverb_var)
        self.scl_reverb.pack(fill=tk.X)

        # Chorus
        lbl_chorus = tk.Label(main_frame, text="● Chorus (CC#93):")
        lbl_chorus.pack(anchor="w", pady=(10,0))
        self.chorus_var = tk.IntVar(value=20)
        self.scl_chorus = tk.Scale(main_frame, from_=0, to=127, orient=tk.HORIZONTAL,
                                   variable=self.chorus_var)
        self.scl_chorus.pack(fill=tk.X)

        # Button frame
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        btn_generate = tk.Button(btn_frame, text="Generate MIDI File",
                                 command=self.on_generate_midi)
        btn_generate.pack(side=tk.LEFT, padx=10)

        btn_exit = tk.Button(btn_frame, text="Exit", command=self.on_exit)
        btn_exit.pack(side=tk.RIGHT, padx=10)

    def on_exit(self):
        self.destroy()

    def on_generate_midi(self):
        """Generate MIDI so that melody & drums finish at the same time."""
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Text is empty.")
            return
        words = re.split(r"\s+", text)
        words = [re.sub(r"[,\.\?!;:]", "", w) for w in words if w.strip()]
        if not words:
            messagebox.showwarning("Warning", "No valid words found.")
            return

        word_lengths = [len(w) for w in words]
        min_len, max_len = min(word_lengths), max(word_lengths)

        # Scale
        scale_name = self.scale_var.get()
        if scale_name not in SCALE_OPTIONS:
            messagebox.showerror("Error", "Invalid Scale selection.")
            return
        scale_intervals = SCALE_OPTIONS[scale_name]

        # Key
        key_name = self.key_var.get()
        if key_name not in KEY_OPTIONS:
            messagebox.showerror("Error", "Invalid Key selection.")
            return
        base_note = KEY_OPTIONS[key_name]

        # BPM
        bpm = self.bpm_var.get()
        if bpm <= 0:
            messagebox.showerror("Error", "BPM must be >= 1.")
            return

        # Reverb & Chorus
        reverb_amount = self.reverb_var.get()
        chorus_amount = self.chorus_var.get()

        # 1) Melody generation
        n_scales = len(scale_intervals)
        splitted_ranges = np.array_split(range(min_len, max_len+1), n_scales)
        mapped_indices = []
        for length in word_lengths:
            for idx, seg in enumerate(splitted_ranges):
                if seg[0] <= length <= seg[-1]:
                    mapped_indices.append(idx)
                    break

        tempo_val = mido.bpm2tempo(bpm)
        mid = MidiFile()

        # -- Melody Track (channel=0) --
        melody_track = MidiTrack()
        mid.tracks.append(melody_track)

        # Set tempo & Program Change
        melody_track.append(MetaMessage('set_tempo', tempo=tempo_val))
        melody_track.append(Message('program_change', program=0, channel=0, time=0))  # Piano
        # Main Volume & Effects
        melody_track.append(Message('control_change', channel=0, control=7, value=127, time=0))
        melody_track.append(Message('control_change', channel=0, control=91, value=reverb_amount, time=0))
        melody_track.append(Message('control_change', channel=0, control=93, value=chorus_amount, time=0))

        note_durations = [480, 960, 1920]  # Quarter(480), Half(960), Whole(1920)
        current_time_melody = 0
        for idx in mapped_indices:
            note_num = base_note + scale_intervals[idx]
            dur = random.choice(note_durations)
            velocity = random.randint(90, 127)  # louder
            # Note ON
            melody_track.append(Message('note_on', note=note_num, velocity=velocity,
                                        time=0, channel=0))
            # Note OFF
            melody_track.append(Message('note_off', note=note_num, velocity=0,
                                        time=dur, channel=0))
            current_time_melody += dur

        total_melody_ticks = current_time_melody

        # -- Drum Track (channel=9) --
        drum_track = MidiTrack()
        mid.tracks.append(drum_track)

        drum_track.append(MetaMessage('set_tempo', tempo=tempo_val))
        # Main Volume, Reverb, Chorus for Drums
        drum_track.append(Message('control_change', channel=9, control=7, value=127, time=0))
        drum_track.append(Message('control_change', channel=9, control=91, value=reverb_amount, time=0))
        drum_track.append(Message('control_change', channel=9, control=93, value=chorus_amount, time=0))

        # Generate drums until melody finishes
        generate_drum_to_fit_time(drum_track, total_melody_ticks, channel=9)

        # 2) Save the MIDI file
        file_path = filedialog.asksaveasfilename(
            title="Save MIDI File",
            defaultextension=".mid",
            filetypes=[("MIDI File", "*.mid"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                mid.save(file_path)
                messagebox.showinfo("Success", f"MIDI file saved:\n{file_path}")
            except ValueError as e:
                messagebox.showerror("Error", f"Failed to save MIDI:\n{e}")


#######################################
# 6. Main
#######################################
if __name__ == "__main__":
    app = TextToMidiSyncApp()
    app.mainloop()
