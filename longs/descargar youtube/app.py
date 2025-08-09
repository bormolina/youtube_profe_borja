from flask import Flask, render_template, request, send_file, abort
import subprocess, os, tempfile, uuid, zipfile, shlex

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/descargar-file', methods=['POST'])
def descargar_file():
    url     = request.form.get('url')
    formato = request.form.get('formato')
    partes  = request.form.get('partes', '').strip()  # segundo parámetro es valor por defecto

    if not url or not formato:
        abort(400, 'Faltan parámetros')

    # carpeta temporal para este trabajo
    workdir = tempfile.mkdtemp(prefix="dl_")
    # nombre base “seguro”
    base = f"descarga_{uuid.uuid4().hex}"

    if formato == 'mp3':
        # yt-dlp pondrá .mp3 tras extraer (requiere ffmpeg)
        fmt_args = ["-f", "bestaudio", "--extract-audio", "--audio-format", "mp3"]
    else:
        # prioriza vídeo+audio en el contenedor elegido y remuxea a mp4 si toca
        fmt_args = ["-f", f"bestvideo[ext={formato}]+bestaudio/best[ext={formato}]"]
        if formato == "mp4":
            fmt_args += ["--remux-video", "mp4"]

    script_path = os.path.join(os.path.dirname(__file__), "yt-dlp")

    # --- NUEVO: gestionar 'partes' en 2 modos: tiempos o playlist ---
    ran_once = False  # para saber si ya ejecutamos yt-dlp
    if partes:
        # ---- TRAMOS DE TIEMPO: un yt-dlp por tramo, nombre único por tramo ----
        tramos = [p.strip() for p in partes.split(",") if p.strip()]
        for i, tramo in enumerate(tramos, start=1):
            out_tmpl_i = os.path.join(workdir, f"{base}.{i:02d}.%(ext)s")
            cmd = ["python3", script_path, url,
                    "-o", out_tmpl_i, "--no-progress",
                    "--download-sections", f"*{tramo}"] + fmt_args
            app.logger.info("Ejecutando (tramo %s): %s", i, " ".join(shlex.quote(c) for c in cmd))
            try:
                subprocess.run(cmd, check=True, text=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                return f"<pre>Error en yt-dlp (tramo {i} {tramo}):\nSTDOUT:\n{e.stdout}\n\nSTDERR:\n{e.stderr}</pre>", 500
        ran_once = True  # ya hicimos todas las ejecuciones por tramo

    if not ran_once:
        # ---- SIN PARTES: una sola descarga normal ----
        out_tmpl = os.path.join(workdir, base + ".%(ext)s")
        cmd = ["python3", script_path, url, "-o", out_tmpl, "--no-progress"] + fmt_args
        app.logger.info("Ejecutando: %s", " ".join(shlex.quote(c) for c in cmd))
        try:
            subprocess.run(cmd, check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            return f"<pre>Error en yt-dlp:\nSTDOUT:\n{e.stdout}\n\nSTDERR:\n{e.stderr}</pre>", 500

    # Detectar archivos generados
    files = [os.path.join(workdir, f) for f in os.listdir(workdir)
             if os.path.isfile(os.path.join(workdir, f))]
    if not files:
        return "No se generó ningún archivo.", 500

    # Si hay más de un fichero, empaquetamos en ZIP.
    if len(files) > 1:
        zip_path = os.path.join(workdir, base + ".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, arcname=os.path.basename(f))
        return send_file(zip_path, as_attachment=True, download_name=os.path.basename(zip_path))
    else:
        final_path = files[0]
        download_name = os.path.basename(final_path)
        return send_file(final_path, as_attachment=True, download_name=download_name)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)