#!/usr/bin/env python3
"""Conferidor do ARCKHÉ Learning 7.13.16 â€” as MESMAS regras do assets/v72-conferidor.js (seÃ§Ã£o "conferidor").

O aluno escreve um arquivo (ficha, cartÃ£o, decupagem) e a pÃ¡gina confere. Este script Ã© a opÃ§Ã£o para quem tem
terminal: confere o mesmo arquivo, com as regras escritas no JSON da aula.

    python3 conferir.py                          # lista as aulas que tÃªm conferidor
    python3 conferir.py <aula> <arquivo.txt>     # confere o seu arquivo
    python3 conferir.py <aula> --exemplo         # confere o exemplo que passa (ensaio)
    python3 conferir.py <aula> --errado          # confere o exemplo com erro
    python3 conferir.py <aula> ... --lang en     # regras e mensagens em inglÃªs (conteudo/en)

Sai 0 quando passa ("OK: ...") e 1 quando falta algo. Regras (lista "regras" da seÃ§Ã£o):
  campos      {campos: [rÃ³tulos], min}       cada rÃ³tulo numa linha "RÃ³tulo: texto" com pelo menos <min> letras
  planos      {min, max}                     linhas que comeÃ§am por nÃºmero ("1 | ...", "2. ...") = planos
  cada_plano  {grupos: [{rot, termos, um_so?, variar?, min?}]}
              cada plano tem um termo de cada grupo; "a / b / c" num termo = sinÃ´nimos (contam como um);
              um_so: no mÃ¡ximo uma famÃ­lia por plano; variar: N famÃ­lias diferentes no conjunto;
              min: rÃ³tulo ("som:") sÃ³ vale com >= min letras depois dele, atÃ© o prÃ³ximo |
  duracao     {min, max}                     cada plano tem "N s"; a soma fica entre min e max
  termos      {grupos: [{rot, termos, campo?}]}  o texto todo cita um termo de cada grupo (com campo: sÃ³ a linha "Campo: â€¦")
  video       {min, max, proporcao?, largura_min?}   7.12.15: modo vÃ­deo â€” o argumento Ã© o arquivo de vÃ­deo
              (duraÃ§Ã£o e tamanho pelo ffprobe); proporcao "16:9" ou lista ["16:9", "9:16"]; clipes de exemplo
              em video_ok / video_erro (caminhos no repo)
"""
import json, pathlib, re, sys, unicodedata

RAIZ = pathlib.Path(__file__).resolve().parent
PLANO = re.compile(r"^\s*\d{1,2}\s*[|.)\-â€“â€”]")
DURACAO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:s|seg|segundos?|seconds?|sec)\b")
UI = {  # padrÃµes (iguais a CONF_UI do gerar.py); o curso.json â†’ ui pode trocar e traduzir
    "conf_vazio": "Cole o texto ou carregue o arquivo antes de conferir.",
    "conf_falta": "Ainda nÃ£o. O que falta:",
    "conf_campo": "Falta a linha {c}: com a descriÃ§Ã£o (pelo menos {x} letras).",
    "conf_planos": "Achei {n} planos numerados; o pedido Ã© de {x} a {y}. Comece cada plano pelo nÃºmero (1 | ...).",
    "conf_no_plano": "Plano {i}: falta {g}.",
    "conf_um_so": "Plano {i}: {n} escolhas de {g}; fique com uma sÃ³.",
    "conf_variedade": "SÃ³ {n} tipo(s) diferente(s) de {g} nos planos; varie para pelo menos {x}.",
    "conf_sem_duracao": "Plano {i}: falta a duraÃ§Ã£o em segundos (ex.: 4 s).",
    "conf_duracao": "Os planos somam {s} s; o pedido Ã© de {x} a {y} s.",
    "conf_termo": "Falta citar {g}.",
    "conf_mais": "â€¦ e mais {n}.",
    # 7.12.15: modo vÃ­deo (regra "video")
    "conf_video_dur": "O vÃ­deo tem {s} s; o pedido Ã© de {x} a {y} s.",
    "conf_video_prop": "O vÃ­deo Ã© {w}Ã—{h} ({p}); o pedido Ã© {q}.",
    "conf_video_larg": "O vÃ­deo tem {w} px de largura; o mÃ­nimo Ã© {x} px.",
    "conf_video_ler": "NÃ£o consegui ler este vÃ­deo. Exporte em MP4 (H.264) ou WebM e tente de novo.",
}

PROPORCOES = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:5": 4 / 5, "4:3": 4 / 3, "2.39:1": 2.39, "1.85:1": 1.85}


def regra_video(sec):
    """7.12.15: a regra {tipo: "video", min, max, proporcao?, largura_min?} do conferidor, ou None (modo texto)."""
    return next((r for r in sec.get("regras", []) if r.get("tipo") == "video"), None)


def nome_proporcao(w, h):
    """1920Ã—1080 â†’ '16:9'; fora das conhecidas (2 % de folga), a razÃ£o reduzida ('5:3')."""
    if not w or not h:
        return "?"
    for nome, v in PROPORCOES.items():
        if abs(w / h - v) / v <= 0.03:  # 7.13.16: 3 % (1280Ã—704 do Wan 2.2 5B = 16:9; 2 % recusava)
            return nome
    from math import gcd
    g = gcd(int(w), int(h)) or 1
    return f"{int(w) // g}:{int(h) // g}"


def seg1(v, lang):
    """DuraÃ§Ã£o com uma casa: 8.016 â†’ '8,0' (pt/es) ou '8.0' (en)."""
    s = f"{v:.1f}"
    return s if lang == "en" else s.replace(".", ",")


def conferir_video(info, sec, ui=None, lang="pt"):
    """info = (duraÃ§Ã£o em s, largura, altura) ou None quando o arquivo nÃ£o pÃ´de ser lido. Mesmas mensagens do JS."""
    T = {**UI, **(ui or {})}
    r = regra_video(sec)
    if not info or not info[0] or not info[1]:
        return False, T["conf_falta"], [T["conf_video_ler"]]
    d, w, h = info
    faltas, p = [], nome_proporcao(w, h)
    if not r.get("min", 0) <= round(d, 1) <= r.get("max", 10 ** 6):
        faltas.append(fmt(T["conf_video_dur"], s=seg1(d, lang), x=r.get("min", 0), y=r.get("max", "âˆž")))
    props = r.get("proporcao") or []
    props = [props] if isinstance(props, str) else props
    if props and p not in props:
        faltas.append(fmt(T["conf_video_prop"], w=w, h=h, p=p, q=" / ".join(props)))
    if r.get("largura_min") and w < r["largura_min"]:
        faltas.append(fmt(T["conf_video_larg"], w=w, x=r["largura_min"]))
    if faltas:
        return False, T["conf_falta"], faltas
    return True, fmt(sec["ok"], s=seg1(d, lang), w=w, h=h, p=p), []


def sonda(caminho):
    """(duraÃ§Ã£o, largura, altura) pelo ffprobe; None se nÃ£o houver ffprobe ou o arquivo nÃ£o for vÃ­deo."""
    import subprocess
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height:format=duration", "-of", "json", str(caminho)],
                             capture_output=True, text=True, timeout=60).stdout
        j = json.loads(out or "{}")
        st = (j.get("streams") or [{}])[0]
        return float(j.get("format", {}).get("duration", 0)), int(st.get("width", 0)), int(st.get("height", 0))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def norm(t):
    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def familias(grupo):
    """['close / close-up / primeiro plano', 'plano mÃ©dio'] â†’ [['close', 'close-up', 'primeiro plano'], ['plano medio']]"""
    # 7.13.16: famÃ­lia com " / " (barra entre espaÃ§os) separa sÃ³ ali, e o termo pode ter barra ("out/2026", "16:9")
    return [[norm(x).strip() for x in (fam.split(" / ") if " / " in fam else fam.split("/")) if x.strip()]
            for fam in grupo.get("termos", [])]


def achados(linha, grupos):
    """Para cada grupo, o conjunto de famÃ­lias citadas na linha. Termo dentro de termo maior (de qualquer grupo) nÃ£o conta:
    'extreme close-up' nÃ£o conta tambÃ©m como 'close-up'."""
    ln = norm(linha)
    cand = []  # (inÃ­cio, fim, grupo, famÃ­lia)
    for gi, g in enumerate(grupos):
        for fi, fam in enumerate(familias(g)):
            for termo in fam:
                for m in re.finditer(r"(?<![a-z0-9])" + re.escape(termo) + r"(?![a-z0-9])", ln):
                    cand.append((m.start(), m.end(), gi, fi))
    cand.sort(key=lambda c: -(c[1] - c[0]))
    aceitos, out = [], [set() for _ in grupos]
    for c in cand:
        if any(c[0] < a[1] and a[0] < c[1] for a in aceitos):
            continue
        aceitos.append(c)
        out[c[2]].add(c[3])
    return out


def preenchido(linha, grupo):
    """7.11.14: grupo-rÃ³tulo com "min" (ex.: "som:") sÃ³ conta se depois do rÃ³tulo, atÃ© o prÃ³ximo |, houver >= min letras."""
    ln = norm(linha)
    for fam in familias(grupo):
        for termo in fam:
            for m in re.finditer(r"(?<![a-z0-9])" + re.escape(termo) + r"(?![a-z0-9])", ln):
                resto = ln[m.end():].split("|")[0]
                if len(re.sub(r"[^a-z0-9]", "", resto)) >= grupo["min"]:
                    return True
    return False


def duracao_do_plano(linha):
    """7.11.14: a coluna que Ã© sÃ³ a duraÃ§Ã£o ("4 s") vale primeiro; se nÃ£o houver, a primeira menÃ§Ã£o "N s" da linha."""
    for col in norm(linha).split("|")[1:]:
        m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(?:s|seg|segundos?|seconds?|sec)\s*", col)
        if m:
            return m
    return DURACAO.search(norm(linha))


def num(v, lang):
    s = str(round(v, 1)).rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return s if lang == "en" else s.replace(".", ",")


def fmt(t, **k):
    for a, b in k.items():
        t = t.replace("{" + a + "}", str(b))
    return t


def conferir(texto, sec, ui=None, lang="pt"):
    """Devolve (ok, mensagem, lista de faltas). Mesma ordem e mesmas mensagens do JS."""
    T = {**UI, **(ui or {})}
    linhas = [l for l in (texto or "").splitlines()]
    if not "".join(linhas).strip():
        return False, T["conf_vazio"], []
    faltas, planos, segs = [], [l for l in linhas if PLANO.match(l)], 0.0
    for r in sec.get("regras", []):
        t = r.get("tipo")
        if t == "campos":
            mn = r.get("min", 3)
            for c in r["campos"]:
                pad = re.compile(r"^\s*[-*â€¢]?\s*" + re.escape(norm(c)) + r"\s*:\s*(.*)$")
                ok = False
                for l in linhas:
                    m = pad.match(norm(l))
                    if m and len(re.sub(r"[^a-z0-9]", "", m.group(1))) >= mn:
                        ok = True; break
                if not ok:
                    faltas.append(fmt(T["conf_campo"], c=c, x=mn))
        elif t == "planos":
            if not r.get("min", 1) <= len(planos) <= r.get("max", 99):
                faltas.append(fmt(T["conf_planos"], n=len(planos), x=r.get("min", 1), y=r.get("max", 99)))
        elif t == "cada_plano":
            gs = r["grupos"]
            uso = [set() for _ in gs]
            for i, l in enumerate(planos, 1):
                ach = achados(l, gs)
                for gi, g in enumerate(gs):
                    uso[gi] |= ach[gi]
                    if not ach[gi] or (g.get("min") and not preenchido(l, g)):
                        faltas.append(fmt(T["conf_no_plano"], i=i, g=g["rot"]))
                    elif g.get("um_so") and len(ach[gi]) > 1:
                        faltas.append(fmt(T["conf_um_so"], i=i, n=len(ach[gi]), g=g["rot"]))
            for gi, g in enumerate(gs):
                if planos and g.get("variar") and len(uso[gi]) < g["variar"]:
                    faltas.append(fmt(T["conf_variedade"], n=len(uso[gi]), g=g["rot"], x=g["variar"]))
        elif t == "duracao":
            segs = 0.0
            for i, l in enumerate(planos, 1):
                m = duracao_do_plano(l)
                if not m:
                    faltas.append(fmt(T["conf_sem_duracao"], i=i)); continue
                segs += float(m.group(1).replace(",", "."))
            if planos and not r["min"] <= segs <= r["max"]:
                faltas.append(fmt(T["conf_duracao"], s=num(segs, lang), x=r["min"], y=r["max"]))
        elif t == "termos":
            tudo = "\n".join(linhas)
            for gi, g in enumerate(r["grupos"]):
                alvo = tudo
                if g.get("campo"):  # 7.13.16: sÃ³ a linha "Campo: â€¦" conta
                    pc = re.compile(r"^\s*[-*â€¢]?\s*" + re.escape(norm(g["campo"])) + r"\s*:(.*)$")
                    alvo = "\n".join((pc.match(norm(l)) or [None, ""])[1] for l in linhas)
                if not achados(alvo, r["grupos"])[gi]:
                    faltas.append(fmt(T["conf_termo"], g=g["rot"]))
    if faltas:
        return False, T["conf_falta"], faltas
    n = len(planos) if planos else sum(len(r.get("campos", [])) for r in sec.get("regras", []) if r.get("tipo") == "campos")
    return True, fmt(sec["ok"], n=n, s=num(segs, lang)), []


def secoes(lang="pt"):
    """[(slug da aula, Ã­ndice da seÃ§Ã£o 1..N como no gerar.py, seÃ§Ã£o, ui)] de todos os conferidores do curso."""
    base = RAIZ / "conteudo" / lang
    ui = json.loads((base / "curso.json").read_text()).get("ui", {})
    out = []
    for f in sorted((base / "aulas").glob("*.json")):
        a = json.loads(f.read_text())
        n = 0
        for s in a["secoes"]:
            if s["tipo"] == "links":
                continue
            n += 1
            if s["tipo"] == "conferidor":
                out.append((a["slug"], n, s, ui))
    return out


def main(argv):
    lang = "pt"
    if "--lang" in argv:
        i = argv.index("--lang"); lang = argv[i + 1]; del argv[i:i + 2]
    todas = secoes(lang)
    if not argv:
        for slug, n, s, _ in todas:
            print(f"{slug}  Â·  {re.sub('<[^>]+>', '', s['titulo'])}")
        return 0
    slug = argv[0]
    alvo = [x for x in todas if x[0] == slug]
    if not alvo:
        print(f"a aula '{slug}' nÃ£o tem conferidor; rode sem argumentos para ver a lista"); return 2
    _, _, sec, ui = alvo[0]
    if len(argv) < 2:
        print("uso: python3 conferir.py <aula> <arquivo.txt> | --exemplo | --errado"); return 2
    if regra_video(sec):  # 7.12.15: modo vÃ­deo â€” o argumento Ã© o arquivo de vÃ­deo (ffprobe)
        alvo_v = {"--exemplo": RAIZ / sec.get("video_ok", ""), "--errado": RAIZ / sec.get("video_erro", "")}.get(argv[1], argv[1])
        ok, msg, faltas = conferir_video(sonda(alvo_v), sec, ui, lang)
        print(msg)
        for f in faltas:
            print(" - " + f)
        return 0 if ok else 1
    if argv[1] == "--exemplo":
        texto = sec["exemplo"]
    elif argv[1] == "--errado":
        texto = sec["exemplo_errado"]
    else:
        texto = pathlib.Path(argv[1]).read_text(encoding="utf-8")
    ok, msg, faltas = conferir(texto, sec, ui, lang)
    print(msg)
    for f in faltas:
        print(" - " + f)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
