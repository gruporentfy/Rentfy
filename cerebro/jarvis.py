"""Arranca Jarvis: app web + escucha continua ("Hey Jarvis") + voz.

    python -m cerebro              # todo
    python -m cerebro --sin-escucha  # solo la app web (sin micrófono siempre activo)
    python -m cerebro texto        # modo texto en la terminal
"""

from __future__ import annotations

import argparse
import importlib.util
import threading
import webbrowser

from .cerebro import Cerebro
from .config import Config


def _cargar_voz(config: Config):
    try:
        from .voz.habla import Voz

        return Voz(config)
    except Exception as e:
        print(f"[aviso] Voz local no disponible ({e}). La web usará la voz del navegador.")
        return None


def _cargar_oido(config: Config):
    if importlib.util.find_spec("faster_whisper") is None:
        print("[aviso] Oído no instalado: ejecuta  pip install -e '.[voz]'")
        return None
    from .voz.oido import Oido

    return Oido(config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis, tu asistente personal")
    parser.add_argument("modo", nargs="?", choices=["texto"], help="'texto' para usar la terminal")
    parser.add_argument("--sin-escucha", action="store_true", help="no escuchar 'Hey Jarvis'")
    parser.add_argument("--sin-navegador", action="store_true", help="no abrir la web al arrancar")
    args = parser.parse_args()

    if args.modo == "texto":
        from .cli import main as cli

        return cli()

    import uvicorn

    from .servidor import crear_app

    config = Config()
    cerebro = Cerebro(config)
    voz, oido = _cargar_voz(config), _cargar_oido(config)
    if oido:  # cargar Whisper ya, para que la primera pregunta no espere
        def precargar():
            try:
                oido._cargar()
            except Exception as e:
                print(f"[aviso] No se pudo cargar el oído (Whisper): {e}. Ejecuta: bash instalar_mac.sh")

        threading.Thread(target=precargar, daemon=True).start()

    from .notificaciones import Notificador
    from .programador import Programador

    Programador(cerebro, Notificador(config, cerebro.avisos, voz)).iniciar()

    if not args.sin_escucha and voz and oido and importlib.util.find_spec("openwakeword"):
        from .voz.activacion import Escucha

        escucha = Escucha(config, cerebro, oido, voz)
        threading.Thread(target=escucha.ejecutar, daemon=True, name="escucha").start()

    url = f"http://{'localhost' if config.host == '127.0.0.1' else config.host}:{config.puerto}"
    if config.token:
        url += f"/?token={config.token}"
    print(f"Jarvis en {url.split('?')[0]}")
    if voz:
        threading.Thread(target=voz.decir, args=("Sistemas en línea, señor.",), daemon=True).start()
    if not args.sin_navegador:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(crear_app(cerebro, oido, voz, config.token), host=config.host, port=config.puerto, log_level="warning")
