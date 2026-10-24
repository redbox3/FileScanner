"""Reads dimensions, duration and embedded metadata (EXIF, ID3 tags, document properties...)."""

import re
import zipfile
from xml.etree import ElementTree

try:
    from PIL import Image, ExifTags
    Image.MAX_IMAGE_PIXELS = None
except ImportError:  # pragma: no cover
    Image = None

try:  # lets Pillow open iPhone HEIC/HEIF photos (and read their EXIF)
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:  # pragma: no cover
    pass

try:
    from pymediainfo import MediaInfo
    _HAS_MEDIAINFO = MediaInfo.can_parse()
except Exception:  # pragma: no cover
    _HAS_MEDIAINFO = False

try:
    import mutagen
except ImportError:  # pragma: no cover
    mutagen = None

_EXIF_TAGS = getattr(ExifTags, "TAGS", {}) if Image else {}
_GPS_TAGS = getattr(ExifTags, "GPSTAGS", {}) if Image else {}

# Media-info fields worth showing, per track type
_MI_FIELDS = {
    "General": ["format", "format_profile", "overall_bit_rate", "encoded_date", "tagged_date", "recorded_date",
                "writing_application", "encoded_library_name", "title", "performer", "album", "comment", "copyright"],
    "Video": ["format", "codec_id", "width", "height", "display_aspect_ratio", "frame_rate", "frame_rate_mode",
              "bit_rate", "bit_depth", "color_space", "chroma_subsampling", "scan_type", "rotation", "hdr_format"],
    "Audio": ["format", "codec_id", "channel_s", "channel_layout", "sampling_rate", "bit_rate", "bit_depth",
              "compression_mode", "language"],
    "Image": ["format", "width", "height", "bit_depth", "color_space"],
    "Text": ["format", "language", "title"],
}


_FIELD_LABELS = {"channel_s": "channels", "codec_id": "codec ID", "overall_bit_rate": "bit rate"}


def fmt_duration(seconds):
    if seconds is None:
        return ""
    seconds = float(seconds)
    h, rem = divmod(int(round(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _clean(value):
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", "ignore").strip("\x00 ")
        except Exception:
            return ""
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, int) for v in value) and value[1]:
        value = value[0] / value[1]
    if isinstance(value, float):
        value = round(value, 4)
    text = str(value).strip()
    return text if len(text) <= 500 else text[:500] + "..."


def _gps_to_decimal(coord, ref):
    try:
        d, m, s = (float(x) for x in coord)
        value = d + m / 60 + s / 3600
        return round(-value if ref in ("S", "W") else value, 6)
    except Exception:
        return None


def _read_image(path, info):
    if not Image:
        return False
    try:
        with Image.open(path) as img:
            info["width"], info["height"] = img.size
            meta = info["metadata"]
            meta["Image format"] = img.format or ""
            meta["Colour mode"] = img.mode
            if getattr(img, "n_frames", 1) > 1:
                meta["Frames"] = img.n_frames
                if img.format == "GIF":
                    total = 0
                    for i in range(img.n_frames):
                        img.seek(i)
                        total += img.info.get("duration", 0)
                    if total:
                        info["duration"] = total / 1000
            dpi = img.info.get("dpi")
            if dpi:
                meta["DPI"] = f"{round(float(dpi[0]))} x {round(float(dpi[1]))}"
            if img.info.get("icc_profile"):
                meta["ICC profile"] = "embedded"
            exif = img.getexif()
            if exif:
                for tag_id, value in exif.items():
                    name = _EXIF_TAGS.get(tag_id, f"Tag {tag_id}")
                    if name in ("MakerNote", "PrintImageMatching", "ExifOffset", "GPSInfo", "XMLPacket"):
                        continue
                    meta[f"EXIF {name}"] = _clean(value)
                try:
                    for tag_id, value in exif.get_ifd(0x8769).items():  # Exif sub-IFD: camera settings
                        name = _EXIF_TAGS.get(tag_id, f"Tag {tag_id}")
                        if name in ("MakerNote", "UserComment") and isinstance(value, bytes) and len(value) > 64:
                            continue
                        meta[f"EXIF {name}"] = _clean(value)
                except Exception:
                    pass
                try:
                    gps = {_GPS_TAGS.get(k, k): v for k, v in exif.get_ifd(0x8825).items()}
                    if gps:
                        lat = _gps_to_decimal(gps.get("GPSLatitude", ()), gps.get("GPSLatitudeRef"))
                        lon = _gps_to_decimal(gps.get("GPSLongitude", ()), gps.get("GPSLongitudeRef"))
                        if lat is not None and lon is not None:
                            meta["GPS latitude"] = lat
                            meta["GPS longitude"] = lon
                            meta["GPS map link"] = f"https://maps.google.com/?q={lat},{lon}"
                        if "GPSAltitude" in gps:
                            meta["GPS altitude (m)"] = _clean(gps["GPSAltitude"])
                except Exception:
                    pass
                orientation = exif.get(0x0112)
                if orientation in (5, 6, 7, 8):
                    meta["Displayed size (rotated)"] = f"{info['height']} x {info['width']}"
            for key in ("XML:com.adobe.xmp", "Description", "Author", "Software", "Comment", "Title"):
                if key in img.info and key != "XML:com.adobe.xmp":
                    meta[f"Info {key}"] = _clean(img.info[key])
        return True
    except Exception:
        return False


def _read_mediainfo(path, info, category):
    if not _HAS_MEDIAINFO:
        return
    try:
        media = MediaInfo.parse(path)
    except Exception:
        return
    meta = info["metadata"]
    counts = {}
    for track in media.tracks:
        kind = track.track_type
        if kind not in _MI_FIELDS:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        name = "Container" if kind == "General" else kind
        label = name if counts[kind] == 1 else f"{name} {counts[kind]}"
        data = track.to_data()
        if kind == "General" and data.get("duration"):
            info["duration"] = float(data["duration"]) / 1000
        if kind in ("Video", "Image") and info.get("width") is None and data.get("width"):
            info["width"], info["height"] = int(data["width"]), int(data.get("height") or 0)
        if kind == "Video" and data.get("frame_rate"):
            info["frame_rate"] = data["frame_rate"]
        for field in _MI_FIELDS[kind]:
            value = data.get(f"other_{field}", [None])[0] if field in ("overall_bit_rate", "bit_rate", "sampling_rate") else data.get(field)
            if value not in (None, ""):
                meta[f"{label} {_FIELD_LABELS.get(field, field.replace('_', ' '))}"] = _clean(value)
        if kind == "General":
            for key, label in (("xyz", "GPS location"), ("com_apple_quicktime_location_iso6709", "GPS location"),
                               ("com_apple_quicktime_make", "Camera make"), ("com_apple_quicktime_model", "Camera model"),
                               ("com_apple_quicktime_creationdate", "Date recorded")):
                if data.get(key):
                    meta[label] = _clean(data[key])
    if counts:
        meta["Tracks"] = ", ".join(f"{n} {k.lower()}" for k, n in counts.items() if k != "General")


def _read_audio_tags(path, info):
    if not mutagen:
        return
    try:
        audio = mutagen.File(path, easy=True)
    except Exception:
        return
    if not audio:
        return
    if getattr(audio, "info", None) and getattr(audio.info, "length", None) and not info.get("duration"):
        info["duration"] = audio.info.length
    try:
        for key, value in (audio.tags or {}).items():
            if isinstance(value, list):
                value = "; ".join(str(v) for v in value)
            info["metadata"][f"Tag {key}"] = _clean(value)
    except Exception:
        pass


_OFFICE_NS = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
}


def _read_office(path, info):
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            meta = info["metadata"]
            if "docProps/core.xml" in names:
                root = ElementTree.fromstring(z.read("docProps/core.xml"))
                for tag, label in (("dc:title", "Title"), ("dc:subject", "Subject"), ("dc:creator", "Author"),
                                   ("cp:lastModifiedBy", "Last modified by"), ("dcterms:created", "Doc created"),
                                   ("dcterms:modified", "Doc modified"), ("cp:revision", "Revision"),
                                   ("cp:keywords", "Keywords"), ("dc:description", "Comments")):
                    el = root.find(tag, _OFFICE_NS)
                    if el is not None and el.text:
                        meta[f"Doc {label}"] = _clean(el.text)
            if "docProps/app.xml" in names:
                root = ElementTree.fromstring(z.read("docProps/app.xml"))
                for tag, label in (("ep:Application", "Application"), ("ep:Pages", "Pages"), ("ep:Words", "Words"),
                                   ("ep:Slides", "Slides"), ("ep:Company", "Company"),
                                   ("ep:TotalTime", "Editing time (min)")):
                    el = root.find(tag, _OFFICE_NS)
                    if el is not None and el.text:
                        meta[f"Doc {label}"] = _clean(el.text)
    except Exception:
        pass


_PDF_FIELDS = re.compile(rb"/(Title|Author|Creator|Producer|CreationDate|ModDate|Subject)\s*\(([^)]{0,300})\)")


def _read_pdf(path, info):
    try:
        with open(path, "rb") as f:
            head = f.read(2_000_000)
            f.seek(0, 2)
            size = f.tell()
            if size > 2_000_000:
                f.seek(max(0, size - 500_000))
                head += f.read()
        meta = info["metadata"]
        m = re.match(rb"%PDF-(\d\.\d)", head)
        if m:
            meta["PDF version"] = m.group(1).decode()
        pages = re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", head)
        if pages:
            meta["PDF pages"] = max(int(p) for p in pages)
        for key, value in _PDF_FIELDS.findall(head):
            meta.setdefault(f"PDF {key.decode()}", _clean(value))
        if b"/Encrypt" in head:
            meta["PDF encrypted"] = "yes"
    except Exception:
        pass


def read(path, category, ext):
    """Return dict(width, height, duration, frame_rate, metadata={...}) for one file."""
    info = {"width": None, "height": None, "duration": None, "frame_rate": None, "metadata": {}}
    if category == "Image":
        if not _read_image(path, info) or ext in ("heic", "heif", "avif") or info["width"] is None:
            _read_mediainfo(path, info, category)
    elif category in ("Video", "Audio"):
        _read_mediainfo(path, info, category)
        if category == "Audio":
            _read_audio_tags(path, info)
    elif ext in ("docx", "docm", "dotx", "xlsx", "xlsm", "xltx", "pptx", "pptm", "potx", "ppsx"):
        _read_office(path, info)
    elif ext == "pdf":
        _read_pdf(path, info)
    return info
