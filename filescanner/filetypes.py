"""File type knowledge: category, description and the apps likely to open each type."""

import mimetypes
import sys

# extension -> (category, description, mac apps, windows apps)
_TYPES = {}


def _add(category, exts, description, mac, win):
    for ext in exts.split():
        _TYPES[ext] = (category, description, mac, win)


# Images
_add("Image", "jpg jpeg jpe jfif", "JPEG image", "Preview, Photos, Photoshop", "Photos, Paint, Photoshop")
_add("Image", "png", "PNG image", "Preview, Photoshop", "Photos, Paint, Photoshop")
_add("Image", "gif", "GIF image", "Preview, web browser", "Photos, web browser")
_add("Image", "bmp", "Bitmap image", "Preview", "Photos, Paint")
_add("Image", "tif tiff", "TIFF image", "Preview, Photoshop", "Photos, Photoshop")
_add("Image", "webp", "WebP image", "Preview, web browser", "Photos, web browser")
_add("Image", "heic heif", "HEIF image (iPhone)", "Preview, Photos", "Photos (HEIF extension)")
_add("Image", "avif", "AVIF image", "Preview, web browser", "Photos, web browser")
_add("Image", "svg", "SVG vector image", "Web browser, Illustrator, Inkscape", "Web browser, Illustrator, Inkscape")
_add("Image", "ico icns", "Icon file", "Preview", "Photos")
_add("Image", "psd psb", "Photoshop document", "Photoshop, Preview", "Photoshop")
_add("Image", "ai", "Illustrator document", "Illustrator, Preview", "Illustrator")
_add("Image", "eps", "Encapsulated PostScript", "Illustrator, Preview", "Illustrator")
_add("Image", "cr2 cr3 nef arw dng orf rw2 raf srw pef", "Camera RAW image",
     "Photos, Lightroom, Photoshop (Camera Raw)", "Photos, Lightroom, Photoshop (Camera Raw)")
_add("Image", "xcf", "GIMP image", "GIMP", "GIMP")
_add("Image", "indd", "InDesign document", "InDesign", "InDesign")

# Video
_add("Video", "mp4 m4v", "MPEG-4 video", "QuickTime Player, VLC, IINA", "Media Player, Films & TV, VLC")
_add("Video", "mov qt", "QuickTime movie", "QuickTime Player, Final Cut Pro, VLC", "VLC, Media Player, Premiere Pro")
_add("Video", "avi", "AVI video", "VLC, IINA", "Media Player, VLC")
_add("Video", "mkv", "Matroska video", "VLC, IINA", "VLC, Media Player")
_add("Video", "wmv", "Windows Media video", "VLC", "Media Player, VLC")
_add("Video", "webm", "WebM video", "Web browser, VLC", "Web browser, VLC")
_add("Video", "flv", "Flash video", "VLC", "VLC")
_add("Video", "mpg mpeg m2v vob", "MPEG video", "VLC, IINA", "VLC, Media Player")
_add("Video", "mts m2ts ts", "AVCHD / transport stream video", "VLC, Final Cut Pro", "VLC, Premiere Pro")
_add("Video", "3gp 3g2", "3GPP mobile video", "QuickTime Player, VLC", "VLC, Media Player")
_add("Video", "mxf", "MXF broadcast video", "Premiere Pro, DaVinci Resolve, VLC", "Premiere Pro, DaVinci Resolve, VLC")
_add("Video", "braw r3d", "Cinema camera RAW video", "DaVinci Resolve", "DaVinci Resolve")

# Audio
_add("Audio", "mp3", "MP3 audio", "Music, QuickTime Player, VLC", "Media Player, VLC")
_add("Audio", "wav wave", "WAV audio", "Music, QuickTime Player, Audacity", "Media Player, Audacity")
_add("Audio", "aif aiff aifc", "AIFF audio", "Music, QuickTime Player", "VLC, Audacity")
_add("Audio", "m4a aac", "AAC audio", "Music, QuickTime Player", "Media Player, iTunes")
_add("Audio", "flac", "FLAC lossless audio", "VLC, Audacity", "Media Player, VLC")
_add("Audio", "ogg oga opus", "Ogg / Opus audio", "VLC", "VLC, Media Player")
_add("Audio", "wma", "Windows Media audio", "VLC", "Media Player")
_add("Audio", "mid midi", "MIDI music", "GarageBand, Logic Pro", "Media Player")
_add("Audio", "alac caf", "Apple audio", "Music, QuickTime Player", "iTunes, VLC")

# Documents
_add("Document", "pdf", "PDF document", "Preview, Acrobat Reader", "Edge, Acrobat Reader")
_add("Document", "doc docx dot dotx rtf", "Word document", "Word, Pages, TextEdit", "Word, WordPad")
_add("Document", "odt", "OpenDocument text", "LibreOffice, Pages", "LibreOffice, Word")
_add("Document", "pages", "Pages document", "Pages", "(none - export from Pages)")
_add("Document", "txt text log", "Plain text", "TextEdit, any text editor", "Notepad, any text editor")
_add("Document", "md markdown", "Markdown text", "Text editor, Typora", "Notepad, VS Code, Typora")
_add("Document", "epub", "eBook", "Books", "Edge, Calibre")
_add("Document", "mobi azw azw3", "Kindle eBook", "Kindle, Calibre", "Kindle, Calibre")
_add("Spreadsheet", "xls xlsx xlsm xlt xltx", "Excel spreadsheet", "Excel, Numbers", "Excel")
_add("Spreadsheet", "ods", "OpenDocument spreadsheet", "LibreOffice, Numbers", "LibreOffice, Excel")
_add("Spreadsheet", "numbers", "Numbers spreadsheet", "Numbers", "(none - export from Numbers)")
_add("Spreadsheet", "csv tsv", "Comma/tab separated values", "Numbers, Excel, text editor", "Excel, Notepad")
_add("Presentation", "ppt pptx pps ppsx pot potx", "PowerPoint presentation", "PowerPoint, Keynote", "PowerPoint")
_add("Presentation", "key", "Keynote presentation", "Keynote", "(none - export from Keynote)")
_add("Presentation", "odp", "OpenDocument presentation", "LibreOffice, Keynote", "LibreOffice, PowerPoint")

# Archives & disk images
_add("Archive", "zip", "ZIP archive", "Archive Utility, The Unarchiver", "File Explorer, 7-Zip")
_add("Archive", "rar", "RAR archive", "The Unarchiver, Keka", "WinRAR, 7-Zip")
_add("Archive", "7z", "7-Zip archive", "The Unarchiver, Keka", "7-Zip")
_add("Archive", "tar gz tgz bz2 xz zst", "Compressed archive", "Archive Utility", "7-Zip, File Explorer")
_add("Disk image", "dmg", "macOS disk image", "DiskImageMounter (Finder)", "7-Zip (read only)")
_add("Disk image", "iso img", "Disk image", "DiskImageMounter (Finder)", "File Explorer")
_add("Installer", "pkg mpkg", "macOS installer package", "Installer", "(macOS only)")
_add("Installer", "exe msi", "Windows program / installer", "(Windows only)", "Windows")
_add("Installer", "app", "macOS application", "Finder", "(macOS only)")
_add("Installer", "apk", "Android package", "(Android)", "(Android)")

# Web & code
_add("Web", "html htm xhtml", "Web page", "Safari, Chrome, code editor", "Edge, Chrome, code editor")
_add("Web", "css", "Stylesheet", "Code editor", "Code editor")
_add("Code", "js mjs cjs ts tsx jsx", "JavaScript / TypeScript", "VS Code, code editor", "VS Code, code editor")
_add("Code", "php", "PHP script", "VS Code, code editor", "VS Code, code editor")
_add("Code", "py", "Python script", "VS Code, Python", "VS Code, Python")
_add("Code", "sh zsh bash command", "Shell script", "Terminal, code editor", "WSL, Git Bash, code editor")
_add("Code", "bat cmd ps1", "Windows script", "Code editor", "Command Prompt, PowerShell")
_add("Code", "c h cpp hpp cs java swift go rs rb kt", "Source code", "Xcode, VS Code", "Visual Studio, VS Code")
_add("Data", "json xml yaml yml toml ini cfg conf plist", "Data / config file", "Text editor, Xcode", "Notepad, VS Code")
_add("Data", "sql db sqlite sqlite3", "Database", "DB Browser for SQLite, TablePlus", "DB Browser for SQLite, SSMS")

# Fonts
_add("Font", "ttf otf woff woff2 ttc dfont", "Font", "Font Book", "Font Viewer")

# Design / 3D / misc
_add("Design", "sketch", "Sketch design", "Sketch", "(macOS only)")
_add("Design", "fig", "Figma file", "Figma", "Figma")
_add("Design", "xd", "Adobe XD design", "Adobe XD", "Adobe XD")
_add("Design", "aep", "After Effects project", "After Effects", "After Effects")
_add("Design", "prproj", "Premiere Pro project", "Premiere Pro", "Premiere Pro")
_add("Design", "fcpbundle fcpxml", "Final Cut Pro project", "Final Cut Pro", "(macOS only)")
_add("Design", "drp", "DaVinci Resolve project", "DaVinci Resolve", "DaVinci Resolve")
_add("3D / CAD", "obj fbx stl blend dae 3ds gltf glb usdz", "3D model", "Preview (some), Blender", "3D Viewer, Blender")
_add("3D / CAD", "dwg dxf", "AutoCAD drawing", "AutoCAD, DWG viewer", "AutoCAD, DWG TrueView")
_add("3D / CAD", "skp", "SketchUp model", "SketchUp", "SketchUp")
_add("Email", "eml emlx msg mbox", "Email message", "Mail", "Outlook, Mail")
_add("Contact", "vcf ics", "Contact / calendar file", "Contacts, Calendar", "Outlook, People")
_add("Shortcut", "lnk url webloc", "Shortcut / link", "Finder", "File Explorer")
_add("System", "ds_store", "Finder folder settings (hidden)", "(system file)", "(macOS system file)")
_add("System", "ini_win db_thumbs", "Windows system file", "(system file)", "(system file)")
_add("Subtitle", "srt vtt ass ssa", "Subtitles", "Text editor, VLC", "Notepad, VLC")
_add("Lighting / AV", "mvr gdtf", "Lighting visualiser file", "Vectorworks, Capture, grandMA3", "Vectorworks, Capture, grandMA3")
_add("Lighting / AV", "qxw", "QLC+ lighting workspace", "QLC+", "QLC+")

_SPECIAL_NAMES = {
    ".ds_store": ("System", "Finder folder settings (hidden)", "(system file)", "(macOS system file)"),
    "thumbs.db": ("System", "Windows thumbnail cache", "(Windows system file)", "(system file)"),
    "desktop.ini": ("System", "Windows folder settings", "(Windows system file)", "(system file)"),
    "icon\r": ("System", "Custom folder icon", "(system file)", "(macOS system file)"),
}

mimetypes.init()


def describe(filename):
    """Return (extension, category, description, mime, probable apps for this OS, mac apps, windows apps)."""
    lower = filename.lower()
    ext = lower.rsplit(".", 1)[-1] if "." in lower.lstrip(".") else ""
    if lower in _SPECIAL_NAMES:
        category, description, mac, win = _SPECIAL_NAMES[lower]
    elif lower.startswith("._"):
        category, description, mac, win = ("System", "macOS resource fork (AppleDouble)", "(system file)", "(created by macOS)")
    elif ext in _TYPES:
        category, description, mac, win = _TYPES[ext]
    else:
        category, description, mac, win = ("Other", f"{ext.upper()} file" if ext else "File (no extension)", "Unknown", "Unknown")
    mime = mimetypes.guess_type(filename)[0] or ""
    here = win if sys.platform.startswith("win") else mac
    return ext, category, description, mime, here, mac, win


def category_for(filename):
    return describe(filename)[1]
