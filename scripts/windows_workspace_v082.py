"""SONIC V0.8.2 local workspace-only folder operations.

This module is intentionally independent of the cloud policy implementation:
even a malformed/compromised request cannot escape the configured workspace.
"""
from pathlib import Path
import re

RESERVED={'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}
PROTECTED={'.git','.ssh','.aws','.config','.venv','secrets','credentials'}


def validate_relative_folder(raw: str) -> str:
    if not isinstance(raw,str) or not 1<=len(raw.strip())<=180:
        raise PermissionError('FOLDER_NAME_REQUIRED')
    raw=raw.strip().replace('\\','/')
    if raw.startswith(('/', '~')) or re.match(r'^[A-Za-z]:',raw):
        raise PermissionError('WORKSPACE_RELATIVE_ONLY')
    parts=raw.split('/')
    if len(parts)>5 or any(not 1<=len(p)<=70 for p in parts):
        raise PermissionError('FOLDER_DEPTH_OR_LENGTH')
    for p in parts:
        if p in ('.','..') or p[-1] in (' ','.') or p.casefold() in PROTECTED:
            raise PermissionError('UNSAFE_FOLDER_NAME')
        if p.split('.')[0].upper() in RESERVED:
            raise PermissionError('WINDOWS_RESERVED_NAME')
        if any(ord(c)<32 or c in '<>:"|?*$%' for c in p):
            raise PermissionError('UNSAFE_FOLDER_CHARACTER')
    return '/'.join(parts)


def create_folder(root: Path, relative: str) -> dict:
    safe=validate_relative_folder(relative)
    root=Path(root).resolve(strict=True)
    if not root.is_dir():
        raise PermissionError('WORKSPACE_ROOT_UNAVAILABLE')
    parts=safe.split('/')
    current=root
    for part in parts:
        current=current/part
        if current.is_symlink():
            raise PermissionError('SYMLINK_FOLDER_BLOCKED')
    target=current.resolve(strict=False)
    if target==root or root not in target.parents:
        raise PermissionError('OUTSIDE_SONIC_WORKSPACE')
    was_present=target.exists()
    if was_present and not target.is_dir():
        raise PermissionError('EXISTING_PATH_IS_FILE')
    target.mkdir(parents=True,exist_ok=True)
    # Verify actual path after creation in case an ancestor was replaced.
    check=target.resolve(strict=True)
    if root not in check.parents:
        raise PermissionError('WORKSPACE_ESCAPE_DETECTED')
    return {'created':not was_present,'exists':True,'relative_path':safe,
            'path':str(check),'scope':'sonic_workspace'}


def workspace_path(root: Path, raw: str, exists: bool=True) -> Path:
    """Resolve relative paths safely, preserving legacy absolute in-root paths."""
    root=Path(root).resolve(strict=True)
    if not isinstance(raw,str) or not raw or len(raw)>500 or '\0' in raw:
        raise PermissionError('INVALID_WORKSPACE_PATH')
    p=Path(raw)
    target=(p if p.is_absolute() else (root/p))
    resolved=target.resolve(strict=exists)
    if resolved!=root and root not in resolved.parents:
        raise PermissionError('WORKSPACE_ONLY')
    return resolved


def desktop_folder_root() -> Path:
    """Resolve the logged-in Windows user's actual Desktop, including OneDrive redirection.

    Do not create missing Desktop roots and never use a guessed public or
    administrator Desktop; the Scheduled Task must run as the interactive owner.
    """
    import os
    if os.name != 'nt':
        raise PermissionError('WINDOWS_DESKTOP_ONLY')
    import ctypes
    import uuid
    class GUID(ctypes.Structure):
        _fields_=[('Data1',ctypes.c_ulong),('Data2',ctypes.c_ushort),
                  ('Data3',ctypes.c_ushort),('Data4',ctypes.c_ubyte*8)]
    guid=GUID.from_buffer_copy(uuid.UUID('B4BFCC3A-DB2C-424C-B029-7FE99A87C641').bytes_le)
    location=ctypes.c_wchar_p()
    result=ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid),0,None,ctypes.byref(location))
    if result != 0 or not location.value:
        raise PermissionError('WINDOWS_DESKTOP_NOT_RESOLVED')
    try:
        desktop=Path(location.value).resolve(strict=True)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(location,ctypes.c_void_p))
    home=Path.home().resolve(strict=True)
    if not desktop.is_dir() or home not in desktop.parents:
        raise PermissionError('DESKTOP_OUTSIDE_OWNER_PROFILE')
    return desktop


def create_desktop_folder(name: str, desktop_root: Path | None = None) -> dict:
    """Create exactly one folder under the owner's verified Desktop."""
    safe=validate_relative_folder(name)
    if '/' in safe:
        raise PermissionError('DESKTOP_SINGLE_FOLDER_ONLY')
    desktop=(Path(desktop_root).resolve(strict=True) if desktop_root is not None
             else desktop_folder_root())
    if not desktop.is_dir():
        raise PermissionError('DESKTOP_NOT_A_DIRECTORY')
    target=desktop/safe
    if target.is_symlink():
        raise PermissionError('DESKTOP_SYMLINK_BLOCKED')
    existed=target.exists()
    if existed and not target.is_dir():
        raise PermissionError('DESKTOP_TARGET_IS_FILE')
    target.mkdir(exist_ok=True)
    if target.resolve(strict=True).parent != desktop:
        raise PermissionError('DESKTOP_TARGET_ESCAPE')
    return {'created':not existed,'exists':True,'name':safe,
            'path':str(target.resolve(strict=True)),'scope':'owner_desktop'}
