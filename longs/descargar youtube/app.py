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
    partes  = request.form.get('partes', '').strip() # segundo parámetro es valor por defecto

    if not url or not formato:
        abort(400, 'Faltan parámetros')

    # carpeta temporal para este trabajo
    workdir = tempfile.mkdtemp(prefix="dl_")
    # nombre para el fichero, para no volverme loco con los espacios
    base = f"descarga_{uuid.uuid4().hex}"

    if formato == 'mp3':
        out_tmpl = os.path.join(workdir, base + ".%(ext)s")  # yt-dlp pondrá .mp3 tras extraer
        fmt_args = ["-f", "bestaudio", "--extract-audio", "--audio-format", "mp3"]
    else:
        out_tmpl = os.path.join(workdir, base + ".%(ext)s")
        fmt_args = ["-f", f"bestvideo[ext={formato}]+bestaudio/best[ext={formato}]", "--remux-video", "mp4"]

    # script yt-dlp local (sin pip), en la misma carpeta que app.py
    script_path = os.path.join(os.path.dirname(__file__), "yt-dlp")

    cmd = ["python3", script_path, url, "-o", out_tmpl, "--no-progress"] + fmt_args
    if partes:
        for tramo in [p.strip() for p in partes.split(",") if p.strip()]:
            cmd += ["--download-sections", f"*{tramo}"]

    app.logger.info("Ejecutando: %s", " ".join(shlex.quote(c) for c in cmd))

    # Esto bloquea hasta que termine la descarga (el navegador mostrará la descarga
    # solo cuando empecemos a enviar el archivo)
    try:
        subprocess.run(cmd, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        return f"<pre>Error en yt-dlp:\nSTDOUT:\n{e.stdout}\n\nSTDERR:\n{e.stderr}</pre>", 500

    # Detectar archivos generados
    files = [os.path.join(workdir, f) for f in os.listdir(workdir) if os.path.isfile(os.path.join(workdir, f))]
    if not files:
        return "No se generó ningún archivo.", 500

    # Si hay más de un fichero empaquetamos en ZIP.
    if len(files) > 1:
        zip_path = os.path.join(workdir, base + ".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, arcname=os.path.basename(f))
        return send_file(zip_path, as_attachment=True, download_name=os.path.basename(zip_path))
    elif len(files) == 1:
        # Un solo archivo: lo devolvemos tal cual
        final_path = files[0]
        download_name = os.path.basename(final_path)
        return send_file(final_path, as_attachment=True, download_name=download_name)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


