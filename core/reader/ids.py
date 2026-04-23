# SPDX-License-Identifier: AGPL-3.0-or-later
# TGC BUS Core (Business Utility System Core)
# Copyright (C) 2025 True Good Craft
#
# This file is part of TGC BUS Core.
#
# TGC BUS Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# TGC BUS Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

import base64
import binascii
import hmac
import hashlib
import os
import re
from typing import Iterable, Optional, Tuple

RID_PREFIX = "local"
RID_VERSION_V2 = "v2"

_LEGACY_SIG_LEN = 10
_V2_SIG_LEN = 32
_HEX_RE = re.compile(r"^[0-9a-f]+$")
_B64_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _sha1_legacy_hex(data: bytes) -> str:
    """Return SHA-1 hex digest using a local implementation for legacy RID checks."""

    h0 = 0x67452301
    h1 = 0xEFCDAB89
    h2 = 0x98BADCFE
    h3 = 0x10325476
    h4 = 0xC3D2E1F0

    message = bytearray(data)
    bit_len = len(message) * 8
    message.append(0x80)
    while (len(message) % 64) != 56:
        message.append(0)
    message.extend(bit_len.to_bytes(8, byteorder="big"))

    for chunk_start in range(0, len(message), 64):
        chunk = message[chunk_start : chunk_start + 64]
        w = [0] * 80
        for i in range(16):
            offset = i * 4
            w[i] = int.from_bytes(chunk[offset : offset + 4], byteorder="big")
        for i in range(16, 80):
            x = w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]
            w[i] = ((x << 1) | (x >> 31)) & 0xFFFFFFFF

        a, b, c, d, e = h0, h1, h2, h3, h4
        for i in range(80):
            if i < 20:
                f = (b & c) | ((~b) & d)
                k = 0x5A827999
            elif i < 40:
                f = b ^ c ^ d
                k = 0x6ED9EBA1
            elif i < 60:
                f = (b & c) | (b & d) | (c & d)
                k = 0x8F1BBCDC
            else:
                f = b ^ c ^ d
                k = 0xCA62C1D6

            temp = (((a << 5) | (a >> 27)) + f + e + k + w[i]) & 0xFFFFFFFF
            e = d
            d = c
            c = ((b << 30) | (b >> 2)) & 0xFFFFFFFF
            b = a
            a = temp

        h0 = (h0 + a) & 0xFFFFFFFF
        h1 = (h1 + b) & 0xFFFFFFFF
        h2 = (h2 + c) & 0xFFFFFFFF
        h3 = (h3 + d) & 0xFFFFFFFF
        h4 = (h4 + e) & 0xFFFFFFFF

    return "".join(f"{part:08x}" for part in (h0, h1, h2, h3, h4))


def _legacy_root_signature(root: str) -> str:
    digest = _sha1_legacy_hex(_norm(os.path.abspath(root)).encode("utf-8"))
    return digest[:_LEGACY_SIG_LEN]


def root_signature(root: str) -> str:
    digest = hashlib.sha256(("buscore:rid:v2:" + _norm(os.path.abspath(root))).encode("utf-8")).hexdigest()
    return digest[:_V2_SIG_LEN]


def _b64e(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def _b64d(value: str) -> str:
    if not value or not _B64_RE.fullmatch(value):
        raise ValueError("bad_rid")
    mod = len(value) % 4
    if mod == 1:
        raise ValueError("bad_rid")
    padding = "=" * ((4 - mod) % 4)
    try:
        decoded = base64.b64decode((value + padding).encode("ascii"), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("bad_rid") from exc
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("bad_rid") from exc


def _parse_rid(rid: str) -> Tuple[str, str, str]:
    parts = rid.split(":")
    # legacy grammar: local:<sig10>:<payload>
    if len(parts) == 3 and parts[0] == RID_PREFIX:
        _, signature, payload = parts
        if len(signature) != _LEGACY_SIG_LEN or not _HEX_RE.fullmatch(signature):
            raise ValueError("bad_rid")
        return ("legacy", signature, payload)
    # v2 grammar: local:v2:<sig32>:<payload>
    if len(parts) == 4 and parts[0] == RID_PREFIX and parts[1] == RID_VERSION_V2:
        _, _, signature, payload = parts
        if len(signature) != _V2_SIG_LEN or not _HEX_RE.fullmatch(signature):
            raise ValueError("bad_rid")
        return (RID_VERSION_V2, signature, payload)
    raise ValueError("bad_rid")


def _resolve_under_root(root: str, rel: str) -> str:
    if not rel or "\x00" in rel:
        raise ValueError("bad_rid")
    if os.path.isabs(rel):
        raise ValueError("rid_path_escape")
    drive, _ = os.path.splitdrive(rel)
    if drive:
        raise ValueError("rid_path_escape")

    rel_norm = os.path.normpath(rel)
    if rel_norm == ".." or rel_norm.startswith(".." + os.sep):
        raise ValueError("rid_path_escape")

    root_abs = os.path.abspath(root)
    candidate = os.path.normpath(os.path.join(root_abs, rel_norm))
    root_norm = _norm(root_abs)
    candidate_norm = _norm(os.path.abspath(candidate))
    if candidate_norm != root_norm and not candidate_norm.startswith(root_norm.rstrip("\\/") + os.sep):
        raise ValueError("rid_path_escape")
    return candidate


def match_allowed_root(abs_path: str, allowed_roots: Optional[Iterable[str]]):
    """Return best matching allowed root.

    Returns tuple of (original_root, normalized_root) or None when not matched.
    """

    norm_path = _norm(os.path.abspath(abs_path))
    best: Optional[Tuple[str, str]] = None
    for root in allowed_roots or []:
        norm_root = _norm(os.path.abspath(root))
        # allow root itself or any child path
        if norm_path == norm_root or norm_path.startswith(norm_root.rstrip("\\/") + os.sep):
            if best is None or len(norm_root) > len(best[1]):
                best = (root, norm_root)
    return best


def to_rid(abs_path: str, allowed_roots: Optional[Iterable[str]]) -> str:
    match = match_allowed_root(abs_path, allowed_roots)
    if not match:
        raise ValueError("path_not_in_allowed_roots")
    root_orig, root_norm = match
    rel_path = os.path.relpath(_norm(abs_path), root_norm)
    return f"{RID_PREFIX}:{RID_VERSION_V2}:{root_signature(root_orig)}:{_b64e(rel_path)}"


def rid_to_path(rid: str, allowed_roots: Optional[Iterable[str]]) -> str:
    rid_kind, signature, payload = _parse_rid(rid)
    rel = _b64d(payload)

    matches: list[str] = []
    for root in allowed_roots or []:
        expected = root_signature(root) if rid_kind == RID_VERSION_V2 else _legacy_root_signature(root)
        if hmac.compare_digest(expected, signature):
            matches.append(root)

    if not matches:
        raise ValueError("rid_root_not_found")

    resolved: dict[str, str] = {}
    for root in matches:
        path = _resolve_under_root(root, rel)
        resolved[_norm(os.path.abspath(path))] = path

    if len(resolved) != 1:
        raise ValueError("rid_ambiguous_root")

    return next(iter(resolved.values()))
