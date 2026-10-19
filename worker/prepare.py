"""Bundle the existing numerical kernels without the Postgres/CLI dependencies."""

from pathlib import Path
from shutil import copyfile

ROOT = Path(__file__).resolve().parent
for package, module in (("epa", "model.py"), ("pridge", "estimator.py"), ("sim", "score.py")):
    source = ROOT.parent / package / "src" / package
    target = ROOT / "src" / package
    target.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", module):
        copyfile(source / name, target / name)
