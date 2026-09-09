"""Site LOCAL do narrador — sobe um servidor na sua máquina para você enviar um
roteiro `.md`/`.txt` e baixar o áudio narrado. 100% local (nada sai da máquina), sem
API paga, e SEM limite de tamanho de roteiro (o arquivo vai no corpo do POST, não numa
URL/issue como no GitHub Pages).

    python -m k_nar.web            # abre em http://127.0.0.1:8000
    python -m k_nar.web --port 9000 --engine xtts

Servidor stdlib (`http.server`, sem dependências novas). A síntese (XTTS) é lenta em
CPU — a página mostra "gerando…" e entrega o WAV quando termina. O motor de voz é
carregado sob demanda; o modelo XTTS (~1.8GB) baixa no 1º uso.
"""

from __future__ import annotations

import argparse
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = """<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>K-NAR — narrador local</title>
<style>
  :root{ --bg:#0f1115; --panel:#171a21; --edge:#262b36; --ink:#e8eaed; --mut:#9aa4b2;
         --acc:#7cc5ff; --acc2:#a6f0c6; --radius:14px; }
  @media (prefers-color-scheme:light){ :root{ --bg:#f6f7f9; --panel:#fff; --edge:#e3e6ea;
         --ink:#1a1d23; --mut:#5b6472; --acc:#1f6feb; --acc2:#1a7f4b; } }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
    font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  .wrap{max-width:640px;margin:0 auto;padding:40px 20px 80px}
  h1{font-size:34px;font-weight:800;letter-spacing:-1px;margin:0}
  h1 span{background:linear-gradient(90deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;color:transparent}
  .tag{color:var(--mut);margin:6px 0 24px}
  .card{background:var(--panel);border:1px solid var(--edge);border-radius:var(--radius);padding:22px}
  .drop{border:2px dashed var(--edge);border-radius:12px;padding:30px;text-align:center;cursor:pointer;transition:.15s}
  .drop:hover,.drop.over{border-color:var(--acc);background:rgba(124,197,255,.06)}
  .drop b{color:var(--acc)} .drop small{color:var(--mut);display:block;margin-top:6px}
  .row{display:flex;gap:14px;flex-wrap:wrap;margin-top:16px}
  .row>div{flex:1;min-width:150px}
  label{display:block;font-size:13px;font-weight:600;margin:0 0 6px;color:var(--mut)}
  input,select{width:100%;background:var(--bg);color:var(--ink);border:1px solid var(--edge);border-radius:10px;padding:10px 11px;font:inherit}
  .go{margin-top:18px;width:100%;background:linear-gradient(90deg,var(--acc),var(--acc2));color:#04121f;
      border:0;border-radius:12px;padding:15px;font-size:17px;font-weight:800;cursor:pointer}
  .go:disabled{filter:grayscale(.6) brightness(.8);cursor:not-allowed}
  .status{margin-top:16px;color:var(--mut);min-height:22px}
  .spin{display:inline-block;width:14px;height:14px;border:2px solid var(--edge);border-top-color:var(--acc);
        border-radius:50%;animation:s .8s linear infinite;vertical-align:-2px;margin-right:8px}
  @keyframes s{to{transform:rotate(360deg)}}
  audio{width:100%;margin-top:16px} .dl{display:inline-block;margin-top:12px;color:var(--acc);font-weight:600}
  .file{margin-top:10px;color:var(--ink);font-size:14px}
</style></head><body>
<div class="wrap">
  <h1>K-<span>NAR</span></h1>
  <p class="tag">Envie um roteiro <b>.md</b>/<b>.txt</b> e baixe a narração. Local, sem limite de tamanho.</p>
  <div class="card">
    <div class="drop" id="drop">
      <b>Escolher arquivo</b> ou arraste aqui<small>.md ou .txt — qualquer tamanho</small>
      <input type="file" id="file" accept=".md,.txt,text/plain,text/markdown" hidden>
    </div>
    <div class="file" id="fileName"></div>
    <div class="row">
      <div><label>Velocidade</label><input type="number" id="velocidade" value="0.97" step="0.01" min="0.6" max="1.6"></div>
      <div><label>Idioma</label><select id="idioma"><option value="pt">Português</option><option value="en">English</option><option value="es">Español</option></select></div>
    </div>
    <div class="row">
      <div><label>Locutor (opcional)</label><input type="text" id="locutor" placeholder="Damien Black (padrão)"></div>
    </div>
    <button class="go" id="go" disabled>Gerar narração</button>
    <div class="status" id="status"></div>
    <audio id="player" controls hidden></audio>
    <a class="dl" id="dl" hidden download>Baixar o áudio</a>
  </div>
</div>
<script>
  var fileText="", fileBase="narracao";
  var drop=document.getElementById("drop"), file=document.getElementById("file");
  var go=document.getElementById("go"), status=document.getElementById("status");
  drop.onclick=function(){file.click()};
  ["dragover","dragenter"].forEach(function(e){drop.addEventListener(e,function(ev){ev.preventDefault();drop.classList.add("over")})});
  ["dragleave","drop"].forEach(function(e){drop.addEventListener(e,function(ev){ev.preventDefault();drop.classList.remove("over")})});
  drop.addEventListener("drop",function(ev){ if(ev.dataTransfer.files[0]) load(ev.dataTransfer.files[0]); });
  file.addEventListener("change",function(){ if(file.files[0]) load(file.files[0]); });
  function load(f){
    fileBase=(f.name||"narracao").replace(/\\.[^.]+$/,"");
    document.getElementById("fileName").textContent="📄 "+f.name;
    f.text().then(function(t){ fileText=t; go.disabled=false; status.textContent=t.length+" caracteres carregados."; });
  }
  go.onclick=function(){
    if(!fileText){ return; }
    go.disabled=true;
    document.getElementById("player").hidden=true; document.getElementById("dl").hidden=true;
    status.innerHTML='<span class="spin"></span>Gerando… (o XTTS em CPU leva alguns minutos; não feche a aba)';
    var q=new URLSearchParams({ velocidade:document.getElementById("velocidade").value,
      idioma:document.getElementById("idioma").value, locutor:document.getElementById("locutor").value,
      nome:fileBase });
    var t0=Date.now();
    fetch("/narrar?"+q.toString(),{method:"POST",headers:{"Content-Type":"text/plain; charset=utf-8"},body:fileText})
      .then(function(r){ if(!r.ok) return r.text().then(function(m){throw new Error(m||r.status)}); return r.blob(); })
      .then(function(b){
        var url=URL.createObjectURL(b);
        var p=document.getElementById("player"); p.src=url; p.hidden=false;
        var d=document.getElementById("dl"); d.href=url; d.download=fileBase+".wav"; d.hidden=false;
        status.textContent="Pronto em "+((Date.now()-t0)/1000).toFixed(0)+"s.";
        go.disabled=false;
      })
      .catch(function(e){ status.textContent="Erro: "+e.message; go.disabled=false; });
  };
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    engine = "xtts"

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"nao encontrado", "text/plain; charset=utf-8")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/narrar":
            self._send(404, b"nao encontrado", "text/plain; charset=utf-8")
            return
        q = urllib.parse.parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length", 0))
        roteiro = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        if not roteiro.strip():
            self._send(400, "roteiro vazio".encode("utf-8"), "text/plain; charset=utf-8")
            return
        try:
            wav = self._narrate(roteiro, q)
        except Exception as e:  # devolve o erro como texto para a página mostrar
            self._send(500, f"falha ao gerar: {e}".encode("utf-8"), "text/plain; charset=utf-8")
            return
        nome = (q.get("nome", ["narracao"])[0] or "narracao")
        self._send(200, wav, "audio/wav",
                   {"Content-Disposition": f'attachment; filename="{nome}.wav"'})

    def _narrate(self, roteiro: str, q: dict) -> bytes:
        from dataclasses import replace

        from k_nar.narrator import narrate_script
        from k_nar.script import parse_script

        script = parse_script(roteiro)
        idioma = q.get("idioma", [""])[0].strip()
        locutor = q.get("locutor", [""])[0].strip()
        vel = q.get("velocidade", [""])[0].strip()
        if idioma:
            script = replace(script, lang=idioma)
        if locutor:
            script = replace(script, locutor=locutor)
        if vel:
            try:
                script = replace(script, speed=float(vel))
            except ValueError:
                pass
        res = narrate_script(script, engine=self.engine)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            res.write_wav(f.name)
            return Path(f.name).read_bytes()

    def log_message(self, fmt, *args):  # log enxuto
        print("[web]", fmt % args)


def run(host: str = "127.0.0.1", port: int = 8000, engine: str = "xtts") -> None:
    Handler.engine = engine
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"K-NAR narrador local em http://{host}:{port}  (motor: {engine}; Ctrl+C para sair)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando.")
        srv.shutdown()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="k_nar.web", description="Site local do narrador.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--engine", "--motor", dest="engine", default="xtts",
                    choices=["xtts", "formante"], help="motor de voz (xtts | formante p/ rascunho)")
    args = ap.parse_args(argv)
    run(host=args.host, port=args.port, engine=args.engine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
