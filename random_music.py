import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re
import random
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage
import numpy as np

########################################
# 1) Instrument Pools and Scale
########################################
TYPE_INSTRUMENTS = {
    "rock":     [29, 30, 31, 24, 25],
    "metal":    [30, 31, 80, 81],
    "pop":      [0, 4, 24, 40, 73],
    "classical":[40, 41, 42, 43, 44, 45, 46],
    "default":  [0, 24, 32, 40, 56, 57, 72, 73, 74],
}

MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11, 12]

########################################
# 2) Drum Patterns & Markov
########################################
DRUM_PATTERN_A = [
    ("K",1), ("H",2), ("H",3), ("H",4),
    ("S",5), ("H",6), ("H",7), ("H",8),
    ("K",9), ("H",10),("H",11),("H",12),
    ("S",13),("H",14),("H",15),("H",16),
]
DRUM_PATTERN_B = [
    ("K",1), ("H",2), ("H",3), ("H",4),
    ("S",5), ("H",6), ("K",7), ("H",8),
    ("K",9), ("H",10),("H",11),("H",12),
    ("S",13),("H",14),("K",15),("H",16),
]
DRUM_PATTERN_C = [
    ("K",1), ("H",2), ("H",3), ("H",4),
    ("S",5), ("H",6), ("S",7), ("H",8),
    ("K",9), ("K",10),("S",11),("S",12),
    ("K",13),("H",14),("S",15),("H",16),
]
DRUM_NOTE_MAP = {"K":36, "S":38, "H":42}

DRUM_MARKOV = {
    "A": [("A", 0.4), ("B", 0.4), ("C", 0.2)],
    "B": [("A", 0.3), ("B", 0.2), ("C", 0.5)],
    "C": [("A", 0.6), ("B", 0.4)]
}

def get_drum_pattern_map():
    return {
        "A": DRUM_PATTERN_A,
        "B": DRUM_PATTERN_B,
        "C": DRUM_PATTERN_C
    }

def choose_next_pattern(current_id):
    if current_id not in DRUM_MARKOV:
        return None
    choices = DRUM_MARKOV[current_id]
    r = random.random()
    accum = 0.0
    for (pat_id, prob) in choices:
        accum += prob
        if r < accum:
            return pat_id
    return None

########################################
# 3) Melody Data Generation (Unify durations)
########################################

def generate_section_data(words, is_chorus=False):
    """
    Generate a 'recipe' of note events (pitch, duration, extra break)
    for each word in 'words'. We do this once so that
    multiple channels can share the exact same durations.
    
    Returns:
      - a list of (note_num, dur, gap)
      - total length in ticks
    """
    section_data = []
    total_length = 0

    if is_chorus:
        note_durations = [480, 960, 1920]
        base_note = 64
    else:
        note_durations = [240, 480, 960]
        base_note = 60

    for w in words:
        l = len(w)
        if l <= 0:
            continue
        idx_scale = l % len(MAJOR_SCALE)
        pitch_offset = MAJOR_SCALE[idx_scale]
        note_num = base_note + pitch_offset

        dur = random.choice(note_durations)
        if is_chorus:
            velocity = random.randint(100,127)
        else:
            velocity = random.randint(80,120)

        # Optionally store velocity if we want separate control,
        # but for simplicity let's store (dur,gap) only,
        # and velocity be decided when we actually place events in the track.
        # However, to replicate EXACT same velocity across channels,
        # we can store velocity here as well.
        stored_velocity = velocity

        # random break
        gap = 0
        if is_chorus:
            gap = random.randint(0, 120)

        section_data.append((note_num, stored_velocity, dur, gap))
        total_length += dur + gap

    return section_data, total_length


def apply_section_data_to_channel(track, section_data, channel, bpm):
    """
    Writes the note events from 'section_data' into the given track,
    for a specific channel. Returns the total ticks used.
    """
    total_used = 0
    for (note_num, velocity, dur, gap) in section_data:
        # Note On
        track.append(Message('note_on', note=note_num, velocity=velocity, time=0, channel=channel))
        # Note Off
        track.append(Message('note_off', note=note_num, velocity=0, time=dur, channel=channel))
        total_used += dur

        if gap > 0:
            # Insert a dummy event for gap
            track.append(Message('note_on', note=note_num, velocity=0, time=gap, channel=channel))
            total_used += gap

    return total_used

########################################
# 4) Melody Tracks for BGM / SONG
########################################

def bgm_mode(mid, text, bpm, music_type="default"):
    """
    BGM: unify all lines, repeat them, generate a single 'section_data',
    then replicate that section_data for each channel so they match EXACT length.
    """
    lines = text.splitlines()
    all_words = []
    for ln in lines:
        wds = re.split(r"\s+", ln)
        wds = [re.sub(r"[,\.\?!;:]", "", w) for w in wds if w.strip()]
        all_words.extend(wds)

    # loop
    loops = 2
    repeated_words = all_words * loops

    # create track for each channel, but unify the random durations
    # so that both channels produce identical length
    section_data, sec_len = generate_section_data(repeated_words, is_chorus=False)

    channels = [0,1]
    track_lengths = []

    for ch in channels:
        track = MidiTrack()
        mid.tracks.append(track)

        # set tempo
        tempo_val = mido.bpm2tempo(bpm)
        track.append(MetaMessage('set_tempo', tempo=tempo_val, time=0))

        # set instrument
        pool = TYPE_INSTRUMENTS.get(music_type, TYPE_INSTRUMENTS["default"])
        program = random.choice(pool)
        track.append(Message('program_change', program=program, channel=ch, time=0))

        # volume
        track.append(Message('control_change', channel=ch, control=7, value=127, time=0))

        used = apply_section_data_to_channel(track, section_data, ch, bpm)
        track_lengths.append(used)

    return max(track_lengths) if track_lengths else 0


def song_mode(mid, text, bpm, music_type="default"):
    """
    SONG mode with A->B->A structure, but we unify the random durations
    for each 'part' so that both channels are identical in length.
    """
    normal_lines = []
    chorus_lines = []

    lines = text.splitlines()
    for ln in lines:
        ln_stripped = ln.lstrip()
        if ln_stripped.startswith(">"):
            # chorus
            chorus_lines.append(ln_stripped[1:].strip())
        else:
            normal_lines.append(ln.strip())

    def lines_to_words(lns):
        ws = []
        for l_ in lns:
            wds = re.split(r"\s+", l_)
            wds = [re.sub(r"[,\.\?!;:]", "", w) for w in wds if w.strip()]
            ws.extend(wds)
        return ws

    a_words = lines_to_words(normal_lines)
    b_words = lines_to_words(chorus_lines)

    if not b_words:
        # no chorus => fallback
        return bgm_mode(mid, text, bpm, music_type)

    # We'll create "section data" for each part (A, B, A)
    A_data, A_len = generate_section_data(a_words, is_chorus=False)
    B_data, B_len = generate_section_data(b_words, is_chorus=True)
    # We'll do: A -> B -> A again
    # The total length is 2*A_len + B_len

    # We unify each channel so they produce exactly the same events
    channels = [0,1]
    track_lengths = []

    for ch in channels:
        track = MidiTrack()
        mid.tracks.append(track)

        # tempo
        tempo_val = mido.bpm2tempo(bpm)
        track.append(MetaMessage('set_tempo', tempo=tempo_val, time=0))

        # instrument
        pool = TYPE_INSTRUMENTS.get(music_type, TYPE_INSTRUMENTS["default"])
        program = random.choice(pool)
        track.append(Message('program_change', program=program, channel=ch, time=0))

        # volume
        track.append(Message('control_change', channel=ch, control=7, value=127, time=0))

        length_total = 0
        # A
        length_total += apply_section_data_to_channel(track, A_data, ch, bpm)
        # B
        length_total += apply_section_data_to_channel(track, B_data, ch, bpm)
        # A again
        length_total += apply_section_data_to_channel(track, A_data, ch, bpm)

        track_lengths.append(length_total)

    return max(track_lengths) if track_lengths else 0

########################################
# 5) Drum Track (unchanged partial measure clamp)
########################################
def create_drum_track(mid: mido.MidiFile, total_length: int, bpm: int):
    track = MidiTrack()
    mid.tracks.append(track)

    tempo_val = mido.bpm2tempo(bpm)
    track.append(MetaMessage('set_tempo', tempo=tempo_val, time=0))
    track.append(Message('control_change', channel=9, control=7, value=127, time=0))

    measure_ticks = 1920
    current_time = 0
    pattern_map = get_drum_pattern_map()
    current_id = random.choice(list(pattern_map.keys()))

    while current_time < total_length:
        leftover = total_length - current_time
        if leftover <= 0:
            break

        if not current_id:
            current_id = random.choice(list(pattern_map.keys()))
        pattern = pattern_map[current_id]

        if leftover >= measure_ticks:
            current_time = write_full_drum_measure(track, pattern, current_time, measure_ticks)
        else:
            current_time = write_partial_drum_measure(track, pattern, current_time, leftover)
            break

        # next pattern
        current_id = choose_next_pattern(current_id)

def write_full_drum_measure(track, pattern, current_time, measure_ticks):
    step_tick = measure_ticks // 16
    accum = 0
    sorted_pat = sorted(pattern, key=lambda x: x[1])

    for (drum_key, step) in sorted_pat:
        event_tick = (step - 1)*step_tick
        delta = event_tick - accum
        accum = event_tick
        if drum_key in DRUM_NOTE_MAP:
            note_num = DRUM_NOTE_MAP[drum_key]
            vel = random.randint(60,100)
            track.append(Message('note_on', note=note_num, velocity=vel, time=delta, channel=9))
            track.append(Message('note_off', note=note_num, velocity=0, time=50, channel=9))
            accum += 50

    remain = measure_ticks - accum
    if remain < 0:
        remain = 0
    track.append(Message('note_on', note=36, velocity=0, time=remain, channel=9))
    return current_time + measure_ticks

def write_partial_drum_measure(track, pattern, current_time, leftover):
    step_tick = 120
    accum = 0
    sorted_pat = sorted(pattern, key=lambda x: x[1])

    for (drum_key, step) in sorted_pat:
        event_tick = (step - 1)*step_tick
        if event_tick > leftover:
            break
        delta = event_tick - accum
        accum = event_tick
        if drum_key in DRUM_NOTE_MAP:
            note_num = DRUM_NOTE_MAP[drum_key]
            vel = random.randint(60,100)
            track.append(Message('note_on', note=note_num, velocity=vel, time=delta, channel=9))
            off_time = 50
            if event_tick + off_time > leftover:
                off_time = leftover - event_tick
                if off_time < 0:
                    off_time = 0
            track.append(Message('note_off', note=note_num, velocity=0, time=off_time, channel=9))
            accum += off_time

        if accum >= leftover:
            break

    remain = leftover - accum
    if remain > 0:
        track.append(Message('note_on', note=36, velocity=0, time=remain, channel=9))
        accum += remain

    return current_time + leftover

########################################
# 6) Detect #rock, #metal, etc.
########################################
def detect_music_type(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return "default"
    first_line = lines[0].strip().lower()
    if first_line.startswith("#"):
        candidate = first_line[1:].split()[0]
        if candidate in TYPE_INSTRUMENTS:
            return candidate
    return "default"

########################################
# 7) GUI
########################################
class BGMSongApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BGM or SONG - Unified Durations to Sync Melody & Drum")
        self.geometry("700x600")

        frm = tk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        lbl_text = tk.Label(frm, text=(
            "Input Text:\n"
            "- #rock / #metal / etc. on first line => instrument style.\n"
            "- SONG mode: lines starting with '>' => chorus (B part).\n"
            "- We unify random note durations for each part, ensuring all melody channels share the same timing.\n"
        ))
        lbl_text.pack(anchor="w")
        self.txt_input = tk.Text(frm, wrap="word", height=14)
        self.txt_input.pack(fill=tk.BOTH, expand=True)

        lbl_bpm = tk.Label(frm, text="Tempo (BPM):")
        lbl_bpm.pack(anchor="w", pady=(10,0))
        self.bpm_var = tk.IntVar(value=120)
        scl_bpm = tk.Scale(frm, from_=40, to=240, orient=tk.HORIZONTAL,
                           variable=self.bpm_var)
        scl_bpm.pack(fill=tk.X)

        lbl_mode = tk.Label(frm, text="Mode:")
        lbl_mode.pack(anchor="w", pady=(10,0))
        self.mode_var = tk.StringVar(value="BGM")
        cmb_mode = ttk.Combobox(frm, textvariable=self.mode_var,
                                values=["BGM","SONG"], state="readonly")
        cmb_mode.pack(fill=tk.X)

        btn_frame = tk.Frame(frm)
        btn_frame.pack(fill=tk.X, pady=10)

        btn_gen = tk.Button(btn_frame, text="Generate MIDI", command=self.on_generate)
        btn_gen.pack(side=tk.LEFT, padx=5)
        btn_ext = tk.Button(btn_frame, text="Exit", command=self.destroy)
        btn_ext.pack(side=tk.RIGHT, padx=5)

    def on_generate(self):
        text = self.txt_input.get("1.0", tk.END).rstrip()
        if not text:
            messagebox.showwarning("Warning","No text input.")
            return

        bpm = self.bpm_var.get()
        if bpm < 1:
            bpm = 120

        mode = self.mode_var.get()
        music_type = detect_music_type(text)

        mid = MidiFile()

        if mode == "BGM":
            total_len = bgm_mode(mid, text, bpm, music_type)
        else:
            total_len = song_mode(mid, text, bpm, music_type)

        # Drums
        create_drum_track(mid, total_length=total_len, bpm=bpm)

        fname = filedialog.asksaveasfilename(
            title="Save MIDI",
            defaultextension=".mid",
            filetypes=[("MIDI Files","*.mid"),("All Files","*.*")]
        )
        if fname:
            try:
                mid.save(fname)
                messagebox.showinfo("Saved", f"MIDI file saved:\n{fname}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save:\n{e}")


########################################
# 8) main
########################################
if __name__ == "__main__":
    app = BGMSongApp()
    app.mainloop()
