"""Historical CI entry point, now validates the explicitly requested V1.4 orb.

The 5,880-dot quality contract was intentionally superseded by the orb mascot.
The new suite checks actual pixels, gestures, voice layering, privacy and layouts.
Legacy motion geometry remains covered in tests/js/motion*.test.cjs.
"""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('e2e_orbit_v140.py')),run_name='__main__')
