"""
03_entrenar_deteccion.py
========================
Entrena el DETECTOR de monedas (YOLO11n) con dataset_det/ y lo guarda en
modelos/monedas_det.pt.

  - Usa la GPU NVIDIA si PyTorch la ve (unos 15-30 min).
  - Sin GPU (CPU) usa automaticamente un modo mas liviano (35 epocas,
    imagenes de 480 px): tarda unas 2-4 horas segun el procesador.
    --rapido hace una prueba corta (20 epocas) para ver que todo funciona.

Uso:
    python 03_entrenar_deteccion.py
    python 03_entrenar_deteccion.py --epocas 80
    python 03_entrenar_deteccion.py --rapido
"""

import argparse
import shutil

import config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epocas", type=int, default=None, help="por defecto 60 (GPU) o 35 (CPU)")
    ap.add_argument("--rapido", action="store_true", help="prueba corta (CPU)")
    args = ap.parse_args()

    import torch
    from ultralytics import YOLO

    yaml = config.DIR_DET / "data.yaml"
    if not yaml.exists():
        raise SystemExit("[X] No existe dataset_det/. Corre primero: python 02_preparar_deteccion.py")

    gpu = torch.cuda.is_available()
    disp = 0 if gpu else "cpu"
    imgsz = config.IMGSZ_DET if gpu else 480
    epocas = args.epocas or (60 if gpu else 35)
    if args.rapido:
        epocas, imgsz = min(epocas, 20), 480
    print(f"\nEntrenando en: {torch.cuda.get_device_name(0) if gpu else 'CPU'}"
          f"  |  epocas={epocas}  imgsz={imgsz}")
    if not gpu:
        print("  [!] Sin GPU: modo liviano, puede tardar 2-4 horas. Deja el PC conectado y sin\n"
              "      suspender. Si se interrumpe, vuelve a correrlo y continua desde el ultimo punto.")

    ultimo = config.RAIZ / "runs" / "detector" / "weights" / "last.pt"
    if _sin_terminar(ultimo) and not args.rapido and input(
            "Hay un entrenamiento sin terminar. Continuarlo? (s/n): ").strip().lower() == "s":
        YOLO(str(ultimo)).train(resume=True)
    else:
        _entrenar(YOLO("yolo11n.pt"), yaml, epocas, imgsz, gpu, disp)
    _evaluar(yaml, imgsz, disp)


def _sin_terminar(ruta):
    """True si hay un entrenamiento que se corto a la mitad (se puede continuar)."""
    if not ruta.exists():
        return False
    try:
        import torch
        ck = torch.load(str(ruta), map_location="cpu", weights_only=False)
        return ck.get("epoch", -1) != -1
    except Exception:
        return False


def _entrenar(modelo, yaml, epocas, imgsz, gpu, disp):
    modelo.train(
        data=str(yaml),
        epochs=epocas,
        imgsz=imgsz,
        batch=16 if gpu else 8,
        device=disp,
        workers=2,
        patience=15,
        fliplr=0.0,            # una moneda espejada no existe
        degrees=0.0,           # el giro ya viene en las composiciones
        hsv_h=0.01, hsv_s=0.3, hsv_v=0.3,
        scale=0.15,            # la camara esta a altura fija: poco cambio de tamano
        mosaic=1.0, close_mosaic=10,
        project=str(config.RAIZ / "runs"),
        name="detector",
        exist_ok=True,
        verbose=False,
    )


def _evaluar(yaml, imgsz, disp):
    from ultralytics import YOLO
    mejor = config.RAIZ / "runs" / "detector" / "weights" / "best.pt"
    config.DIR_MODELOS.mkdir(exist_ok=True)
    shutil.copy2(mejor, config.RUTA_MODELO_DET)
    print(f"\nModelo guardado en {config.RUTA_MODELO_DET}")

    # --- evaluacion por moneda (validacion) -------------------------------
    m = YOLO(str(config.RUTA_MODELO_DET))
    r = m.val(data=str(yaml), imgsz=imgsz, device=disp, verbose=False, plots=True,
              project=str(config.RAIZ / "runs"), name="detector_val", exist_ok=True)
    print("\n=== Resultado en validacion ===")
    print(f"  mAP50: {r.box.map50:.3f}   (1.0 = perfecto; >0.95 es muy bueno)")
    print(f"  Precision: {r.box.mp:.3f}   Recall: {r.box.mr:.3f}\n")
    print(f"  {'Moneda':<15}{'AP50':>7}")
    nombres = m.names
    for i, c in enumerate(r.box.ap_class_index):
        clase = nombres[int(c)]
        print(f"  {config.CLASES[clase][0]:<15}{r.box.ap50[i]:>7.3f}")
    print(f"\nMatriz de confusion: {config.RAIZ / 'runs' / 'detector_val' / 'confusion_matrix.png'}")
    print("Ahora corre:  python 04_interfaz.py")


if __name__ == "__main__":
    main()
