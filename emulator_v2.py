"""Запуск стенда v2 рядом с неизменённым main.py."""
import multiprocessing as mp
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().with_name('risley_v2')))
import app

if __name__=='__main__':
    mp.freeze_support()
    if len(sys.argv)>2 and sys.argv[1]=='--main':
        app.main_path=Path(sys.argv[2]).resolve()
    app.main()
