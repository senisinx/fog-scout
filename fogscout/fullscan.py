"""Manual "scan now": find any map or realm name anywhere on the screen.

Uses the PP-OCRv4 text detector to find text boxes, then scores every box
against the known names with the same lexicon scorer as the banner reader.
Used when the automatic detection missed the intro banner (for example when
the map name is visible in a menu).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from .textnorm import MAIN, name_chars
from .ocr import LexiconScorer, Recognizer, best_path_logp, runtime


class TextDetector:
    def __init__(self, model_path: str, threads: int = 2, max_side: int = 1600):
        ort = runtime()                           # 1.51.1: loaded here, at the first scan (ocr.runtime)
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, int(threads))
        so.log_severity_level = 3
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")   # 1.8.38: no busy wait after a run
        self.session = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.max_side = max_side

    def boxes(self, bgr: np.ndarray):
        """Axis-aligned text boxes (x0, y0, x1, y1) in image coordinates."""
        h, w = bgr.shape[:2]
        ratio = min(1.0, self.max_side / max(h, w))
        rh = max(32, int(round(h * ratio / 32) * 32))
        rw = max(32, int(round(w * ratio / 32) * 32))
        img = cv2.resize(bgr, (rw, rh)).astype(np.float32)
        img = (img / 255.0 - 0.5) / 0.5
        pred = self.session.run(None, {self.input_name: img.transpose(2, 0, 1)[None]})[0][0, 0]
        mask = cv2.dilate((pred > 0.3).astype(np.uint8), np.ones((2, 2), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        sx, sy = w / rw, h / rh
        out = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            if min(bw, bh) < 3:
                continue
            score = float(pred[y:y + bh, x:x + bw][mask[y:y + bh, x:x + bw] > 0].mean())
            if score < 0.5:
                continue
            area = cv2.contourArea(c)
            peri = cv2.arcLength(c, True) or 1.0
            d = area * 1.6 / peri                         # DBNet "unclip"
            x0 = max(0, int((x - d) * sx))
            y0 = max(0, int((y - d) * sy))
            x1 = min(w, int((x + bw + d) * sx))
            y1 = min(h, int((y + bh + d) * sy))
            if y1 - y0 >= 6 and x1 - x0 >= 12:
                out.append((x0, y0, x1, y1))
        return out


@dataclass
class ScanHit:
    kind: str            # "map" or "realm"
    map_id: str | None
    variant: int
    realm: str | None
    text: str
    fit: float
    margin: float


class FullScanner:
    """CR-006 (code review): every recognition model of the catalog (``catalog.by_model``) – the main (Latin) one
    with ``recognizer``, the other scripts with ``pool`` (ocr.ModelPool, None = main model only). With game languages
    in another script alone the main model has no names at all (the scan crashed on an empty lexicon)."""

    def __init__(self, detector: TextDetector, recognizer: Recognizer, catalog, pool=None):
        self.det = detector
        self.rec = recognizer
        self.catalog = catalog
        self.pool = pool
        self.models = []                  # (model, alphabet, names scorer, realms scorer, name → map, realm key → realm)
        for model in getattr(catalog, "models", [MAIN]):
            names, realms, alphabet = catalog.by_model[model]
            if not names and not realms:
                continue
            if model != MAIN and pool is None:
                continue
            own = [h for h in catalog.hypotheses if h.model == model]
            name_to, realm_to = {}, {}
            for h in own:
                name_to.setdefault(h.name_key, (h.map_id, h.variant))
                for r in h.realm_keys:
                    realm_to.setdefault(r, catalog.maps[h.map_id].realm)
            self.models.append((model, alphabet, LexiconScorer(names, alphabet) if names else None,
                                LexiconScorer(realms, alphabet) if realms else None, name_to, realm_to))
        main = next((m for m in self.models if m[0] == MAIN), None)
        # the main model's names (1.49) – kept for callers and tests
        self.alphabet = catalog.alphabet
        self.names, self.realms = (main[2], main[3]) if main else (None, None)

    def _recognizer(self, model):
        return self.rec if model == MAIN else self.pool.get(model)

    def scan(self, frame: np.ndarray, time_budget: float = 4.0):
        t0 = time.time()
        hits = []
        boxes = self.det.boxes(frame)
        # bigger text first (map titles are large)
        boxes.sort(key=lambda b: -(b[3] - b[1]))
        for (x0, y0, x1, y1) in boxes[:80]:
            if time.time() - t0 > time_budget:
                break
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0 or (x1 - x0) < 1.5 * (y1 - y0):
                continue
            for model, alphabet, names, realms, name_to, realm_to in self.models:
                rec = self._recognizer(model)
                if rec is None:
                    continue
                probs = rec.probs(crop)
                g = rec.wide_groups(probs, alphabet)
                bp = best_path_logp(g)
                text = rec.text(probs)
                for kind, scorer, lookup in (("map", names, name_to), ("realm", realms, realm_to)):
                    if scorer is None:
                        continue
                    lp = scorer.score(g)
                    if not len(lp):
                        continue
                    order = np.argsort(-lp)
                    best = scorer.strings[order[0]]
                    if name_chars(best) < (5 if model == MAIN else 4):     # 1.49: "血屋" counts 4
                        continue
                    fit = float(lp[order[0]] - bp)
                    # margin to the best string that means something *else*
                    # (another map/realm, not just another layout variant)
                    target = lookup.get(best)
                    target_id = target[0] if kind == "map" else target
                    second = -1e9
                    for j in order[1:]:
                        other = lookup.get(scorer.strings[j])
                        other_id = other[0] if kind == "map" else other
                        if other_id != target_id:
                            second = float(lp[j])
                            break
                    margin = float(lp[order[0]] - second)
                    if fit < -4.0 or margin < 4.0:
                        continue
                    if kind == "map":
                        mid, var = lookup[best]
                        hits.append(ScanHit("map", mid, var, None, text, fit, margin))
                    else:
                        hits.append(ScanHit("realm", None, 1, lookup.get(best), text, fit, margin))
        hits.sort(key=lambda h: (h.kind != "map", -h.fit - 0.01 * h.margin))
        return hits
