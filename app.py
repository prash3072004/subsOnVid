import os
import uuid
import socket
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
import whisper

# ── Transliteration helper ────────────────────────────────────────────────────

def get_local_ip():
    """Return the machine's LAN IP address (e.g. 192.168.x.x)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def transliterate_to_roman(text):
    """Convert Devanagari Hindi text to Roman (IAST-like) script."""
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
        return transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)
    except Exception:
        return text  # fallback: return original if library fails

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / 'uploads'
OUTPUT_DIR = BASE_DIR / 'outputs'
FONTS_DIR  = BASE_DIR / 'fonts'

for d in [UPLOAD_DIR, OUTPUT_DIR, FONTS_DIR]:
    d.mkdir(exist_ok=True)

# ── Font discovery ────────────────────────────────────────────────────────────

def get_font_internal_name(font_path):
    """Return the internal family/full name stored inside an OTF/TTF file."""
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(str(font_path))
        nt = tt['name']
        # nameID 4 = Full name, 1 = Family name
        for nid in (4, 1):
            for rec in nt.names:
                if rec.nameID == nid:
                    try:
                        return rec.toUnicode()
                    except Exception:
                        pass
    except Exception:
        pass
    return font_path.stem  # fallback: filename without extension


def discover_fonts():
    system = [
        ('Arial',            False),
        ('Impact',           False),
        ('Times New Roman',  False),
        ('Courier New',      False),
        ('Verdana',          False),
        ('Comic Sans MS',    False),
    ]
    fonts = [{'label': name, 'value': name, 'custom': False} for name, _ in system]
    for ext in ('*.otf', '*.ttf'):
        for f in FONTS_DIR.glob(ext):
            name = get_font_internal_name(f)
            fonts.append({'label': f'★ {name}  (Custom)', 'value': name,
                          'custom': True, 'file': f.name})
    return fonts


AVAILABLE_FONTS = discover_fonts()

# ── ASS helpers ───────────────────────────────────────────────────────────────

def _ass_time(seconds):
    seconds = float(seconds)
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_color, alpha=0):
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def build_ass(cues, style):
    font_name    = style.get('fontName', 'Arial')
    font_size    = int(style.get('fontSize', 36))
    font_color   = _ass_color(style.get('fontColor',   '#FFFFFF'))
    outline_col  = _ass_color(style.get('outlineColor','#000000'))
    outline_sz   = float(style.get('outlineSize', 2))
    bold         = -1 if style.get('bold',   False) else 0
    italic       = -1 if style.get('italic', False) else 0
    align        = {'bottom': 2, 'middle': 5, 'top': 8}.get(style.get('position','bottom'), 2)

    bg_enabled   = style.get('bgEnabled', False)
    if bg_enabled:
        # User opacity is 0-100 (100 is solid). ASS alpha is 0-255 (0 is solid, 255 is transparent)
        opacity = int(style.get('bgOpacity', 60))
        ass_alpha = int((100 - opacity) / 100.0 * 255)
        
        # For BorderStyle=3 (Opaque Box):
        # OutlineColour becomes the box color. Outline becomes the box padding.
        outline_col  = _ass_color(style.get('bgColor', '#000000'), alpha=ass_alpha)
        outline_sz   = 15.0  # 15px padding for the box
        border_style = 3
        shadow       = 0
        bg_color     = "&H00000000" # Unused for the box itself, but required for the slot
    else:
        border_style = 1
        shadow       = 0
        bg_color     = "&H00000000"

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{font_color},&H000000FF,"
        # Position 6 is OutlineColour (controls box color when BorderStyle=3)
        # Position 16 is BorderStyle
        # Position 17 is Outline (controls box padding when BorderStyle=3)
        f"{outline_col},{bg_color},{bold},{italic},0,0,100,100,0,0,"
        f"{border_style},{outline_sz},{shadow},{align},10,10,30,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for cue in cues:
        text = str(cue.get('text', '')).strip().replace('\n', '\\N')
        lines.append(
            f"Dialogue: 0,{_ass_time(cue['start'])},{_ass_time(cue['end'])},"
            f"Default,,0,0,0,,{text}"
        )
    return header + '\n'.join(lines) + '\n'

# ── SRT helpers ───────────────────────────────────────────────────────────────

def _srt_time(s):
    s = float(s)
    h   = int(s // 3600)
    m   = int((s % 3600) // 60)
    sec = int(s % 60)
    ms  = int(round((s % 1) * 1000))
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def build_srt(cues):
    parts = []
    for i, cue in enumerate(cues, 1):
        parts.append(f"{i}\n{_srt_time(cue['start'])} --> {_srt_time(cue['end'])}\n{cue['text']}\n")
    return '\n'.join(parts)

# ── N-words-per-screen split ─────────────────────────────────────────────────

def split_n_words(cues, n=1, highlight_color=None):
    """
    Split each cue into chunks of n words. 
    If `highlight_color` is provided (e.g. '&H00FFFF&'), instead of just returning 
    the n words, it returns the n words repeated n times, with each iteration 
    highlighting the i-th active word.
    If n=0, it processes the whole sentence as a single chunk.
    """
    if n > 0:
        n = max(1, int(n))
    result = []
    
    for cue in cues:
        words = str(cue.get('text', '')).strip().split()
        if not words:
            continue
        start, end = float(cue['start']), float(cue['end'])
        
        # If n=0, the chunk is the entire sentence.
        if n == 0:
            chunks = [words]
        else:
            chunks = [words[i:i + n] for i in range(0, len(words), n)]
            
        chunk_dur = (end - start) / len(chunks)
        
        for chunk_idx, chunk in enumerate(chunks):
            chunk_start = start + chunk_idx * chunk_dur
            chunk_end = start + (chunk_idx + 1) * chunk_dur
            
            if highlight_color:
                # Distribute chunk_dur among the words IN this chunk
                word_dur = (chunk_end - chunk_start) / len(chunk)
                for i in range(len(chunk)):
                    highlighted_chunk = []
                    for j, w in enumerate(chunk):
                        if j == i:
                            highlighted_chunk.append(f"{{\\c{highlight_color}}}{w}{{\\c}}")
                        else:
                            highlighted_chunk.append(w)
                    
                    result.append({
                        'start': round(chunk_start + i * word_dur, 3),
                        'end':   round(chunk_start + (i + 1) * word_dur, 3),
                        'text':  ' '.join(highlighted_chunk)
                    })
            else:
                result.append({
                    'start': round(chunk_start, 3),
                    'end':   round(chunk_end, 3),
                    'text':  ' '.join(chunk)
                })
    return result

# ── FFmpeg path escaping (Windows) ────────────────────────────────────────────

def filter_path(p):
    """Escape a filesystem path for use inside an FFmpeg -vf filter string."""
    s = str(p).replace('\\', '/')
    if len(s) >= 2 and s[1] == ':':        # escape drive colon  C:/ -> C\:/
        s = s[0] + '\\:' + s[2:]
    return s

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', fonts=AVAILABLE_FONTS)


@app.route('/upload', methods=['POST'])
def upload():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    video      = request.files['video']
    model_name = request.form.get('model', 'turbo')
    script     = request.form.get('script', 'original')  # 'original' or 'roman'
    ext        = Path(video.filename).suffix.lower() or '.mp4'
    uid        = str(uuid.uuid4())
    filepath   = UPLOAD_DIR / (uid + ext)
    video.save(str(filepath))

    try:
        model  = whisper.load_model(model_name)
        result = model.transcribe(str(filepath), verbose=False)
        cues   = []
        for s in result['segments']:
            text = s['text'].strip()
            if script == 'roman':
                text = transliterate_to_roman(text)
            cues.append({'start': round(s['start'], 3),
                         'end':   round(s['end'],   3),
                         'text':  text})
        return jsonify({'cues': cues, 'filename': filepath.name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/burn', methods=['POST'])
def burn():
    data            = request.get_json(force=True)
    filename        = data.get('filename')
    cues            = data.get('cues', [])
    style           = data.get('style', {})
    mode            = data.get('mode', 'hardcoded')
    words_per_screen = int(data.get('wordsPerScreen', 0))  # 0 = disabled
    sync_offset_ms   = float(data.get('syncOffset', 0))    # milliseconds
    
    highlight_enabled = style.get('highlightEnabled', False)
    highlight_color   = style.get('highlightColor', '#FFFF00')

    if not filename or not cues:
        return jsonify({'error': 'Missing filename or cues'}), 400

    input_path = UPLOAD_DIR / filename
    if not input_path.exists():
        return jsonify({'error': 'Source video not found on server'}), 404

    # Apply chunking and optional ASS highlighting
    hc = _ass_color(highlight_color) if highlight_enabled else None
    
    if words_per_screen > 0 or highlight_enabled:
        cues = split_n_words(cues, words_per_screen, highlight_color=hc)

    # Apply sync offset (convert ms → seconds, clamp start to >= 0)
    if sync_offset_ms != 0:
        offset_s = sync_offset_ms / 1000.0
        cues = [{'start': max(0.0, round(c['start'] + offset_s, 3)),
                 'end':   max(0.0, round(c['end']   + offset_s, 3)),
                 'text':  c['text']} for c in cues]


    uid         = str(uuid.uuid4())
    out_name    = f"output_{uid}.mp4"
    out_path    = OUTPUT_DIR / out_name

    try:
        if mode == 'hardcoded':
            ass_path = OUTPUT_DIR / f"{uid}.ass"
            ass_path.write_text(build_ass(cues, style), encoding='utf-8-sig')

            ap = filter_path(ass_path)
            fd = filter_path(FONTS_DIR)
            cmd = ['ffmpeg', '-y', '-i', str(input_path),
                   '-vf', f"ass='{ap}':fontsdir='{fd}'",
                   '-c:a', 'copy', str(out_path)]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding='utf-8', errors='replace')
            ass_path.unlink(missing_ok=True)

        else:  # softcoded
            srt_path = OUTPUT_DIR / f"{uid}.srt"
            srt_path.write_text(build_srt(cues), encoding='utf-8-sig')

            cmd = ['ffmpeg', '-y', '-i', str(input_path), '-i', str(srt_path),
                   '-c', 'copy', '-c:s', 'mov_text',
                   '-metadata:s:s:0', 'language=eng', str(out_path)]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding='utf-8', errors='replace')
            srt_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            return jsonify({'error': proc.stderr[-1500:]}), 500

        return jsonify({'output': out_name})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/network-info')
def network_info():
    ip = get_local_ip()
    return jsonify({'ip': ip, 'port': 5001, 'url': f'http://{ip}:5001'})


@app.route('/download/<path:filename>')
def download(filename):
    return send_from_directory(str(OUTPUT_DIR), filename, as_attachment=True)


if __name__ == '__main__':
    local_ip = get_local_ip()
    print("\n  SubsOnVid -- Video Subtitle Generator")
    print("=" * 42)
    print(f"   Custom fonts found : {sum(1 for f in AVAILABLE_FONTS if f['custom'])}")
    print(f"   Local (this PC)    : http://127.0.0.1:5001")
    print(f"   On your iPhone     : http://{local_ip}:5001")
    print("   Press Ctrl+C to stop\n")
    app.run(host='0.0.0.0', debug=False, port=5001)
