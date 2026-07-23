"""Validação ESTRITA do JSON da PASSAGEM 1 — o portão na fronteira com o LLM.

O loader de `models.py` é tolerante de propósito (bom para ergonomia e testes).
Mas numa fronteira com IA local, tolerância vira armadilha: "muito alta", "tensa
demais" ou um `tipo` inventado passariam como fallback silencioso, mascarando
falha de direção do modelo. Este validador é o oposto: recusa qualquer coisa fora
do contrato, com mensagem clara. Rode-o ANTES de `Scene.from_dict` em produção.

(Sem dependências. Quando plugarmos o LLM de verdade, dá para trocar por Pydantic
ou JSON Schema — o contrato aqui é a especificação de referência.)
"""

from __future__ import annotations

from typing import Any

from k_nar.models import DramaticPause, EntryType

_ENTRY_TYPES = {e.value for e in EntryType}
_PAUSES = {p.value for p in DramaticPause}
# Discriminador de evento: fala/diálogo, narração, ou som (SFX/ambiência).
_NARRATION_KINDS = {"narracao", "narrador"}
_SOUND_KINDS = {"sfx", "som", "efeito", "ambiencia", "ambience", "ambiente"}
_EVENT_KINDS = {"fala", "dialogo"} | _NARRATION_KINDS | _SOUND_KINDS
# rótulos de distância aceitos (canônicos + apelidos comuns); o ProximityPolicy resolve.
_DISTANCES = {"perto", "proximo", "media", "medio", "longe", "distante",
              "muito_longe", "queima_roupa", "near", "far", "cerca", "lejos"}


class SchemaError(ValueError):
    """Erros de contrato encontrados no JSON do LLM (lista todos de uma vez)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("JSON da cena invalido:\n  - " + "\n  - ".join(errors))


def _num(errs, path, v, lo, hi, required=False):
    if v is None:
        if required:
            errs.append(f"{path}: obrigatorio")
        return
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        errs.append(f"{path}: deve ser numero (recebeu {v!r})")
    elif not (lo <= v <= hi):
        errs.append(f"{path}: fora do intervalo [{lo}, {hi}] (recebeu {v})")


def validate_scene(d: Any, *, allow_numeric_tension: bool = True) -> None:
    """Valida o dict da cena. Levanta `SchemaError` com TODOS os problemas."""
    errs: list[str] = []

    if not isinstance(d, dict):
        raise SchemaError(["raiz: deve ser um objeto JSON"])

    for key in ("cena_id", "ambientacao", "eventos"):
        if key not in d:
            errs.append(f"raiz.{key}: obrigatorio")

    eventos = d.get("eventos")
    if not isinstance(eventos, list) or not eventos:
        errs.append("eventos: deve ser uma lista nao-vazia")
        raise SchemaError(errs)

    seen_ids: set[str] = set()
    for i, ev in enumerate(eventos):
        p = f"eventos[{i}]"
        if not isinstance(ev, dict):
            errs.append(f"{p}: deve ser objeto")
            continue

        eid = ev.get("id")
        if not eid or not isinstance(eid, str):
            errs.append(f"{p}.id: obrigatorio (string)")
        elif eid in seen_ids:
            errs.append(f"{p}.id: duplicado ({eid!r})")
        else:
            seen_ids.add(eid)

        # discriminador de evento (opcional; default = fala)
        kind = str(ev.get("tipo_evento", ev.get("tipo", ""))).strip().lower()
        if kind and kind not in _EVENT_KINDS:
            errs.append(f"{p}.tipo_evento: {kind!r} nao esta em {sorted(_EVENT_KINDS)}")

        # SOM (SFX/ambiência): exige `tag`, não `texto`/`personagem`/`voz`.
        if kind in _SOUND_KINDS:
            if not (ev.get("tag") or ev.get("gatilho") or ev.get("som")):
                errs.append(f"{p}.tag: obrigatorio para {kind}")
            dist = ev.get("distancia", ev.get("distance"))
            if dist is not None and str(dist).strip().lower() not in _DISTANCES:
                errs.append(f"{p}.distancia: {dist!r} nao esta em {sorted(_DISTANCES)}")
            continue

        is_narration = kind in _NARRATION_KINDS or \
            str(ev.get("personagem", "")).strip().lower() in ("narrador", "narrator")

        if not ev.get("texto"):
            errs.append(f"{p}.texto: obrigatorio (nao vazio)")
        # narração dispensa `personagem` (default "Narrador"); diálogo exige.
        if not is_narration and not ev.get("personagem"):
            errs.append(f"{p}.personagem: obrigatorio")

        # voz
        voz = ev.get("voz", {})
        if voz and not isinstance(voz, dict):
            errs.append(f"{p}.voz: deve ser objeto")
        elif isinstance(voz, dict):
            tensao = voz.get("tensao")
            if tensao is not None:
                labels = {"baixa", "media", "alta", "extrema"}
                is_num = isinstance(tensao, (int, float)) and not isinstance(tensao, bool)
                if is_num:
                    if not allow_numeric_tension:
                        errs.append(f"{p}.voz.tensao: use rotulo {sorted(labels)}")
                    else:
                        _num(errs, f"{p}.voz.tensao", tensao, 0.0, 1.0)
                elif str(tensao).strip().lower() not in labels:
                    errs.append(f"{p}.voz.tensao: {tensao!r} nao esta em {sorted(labels)}")
            _num(errs, f"{p}.voz.velocidade", voz.get("velocidade"), 0.3, 2.5)
            _num(errs, f"{p}.voz.tom", voz.get("tom"), -1.0, 1.0)
            # ATUAÇÃO (opcional): emoção (rótulo) + intensidade 0..1
            if voz.get("intensidade") is not None:
                _num(errs, f"{p}.voz.intensidade", voz.get("intensidade"), 0.0, 1.0)
            emo = voz.get("emocao")
            if emo is not None and not isinstance(emo, str):
                errs.append(f"{p}.voz.emocao: deve ser texto")

        # entrada
        entrada = ev.get("entrada", {})
        if isinstance(entrada, dict):
            tipo = entrada.get("tipo", EntryType.SEQUENTIAL.value)
            if tipo not in _ENTRY_TYPES:
                errs.append(f"{p}.entrada.tipo: {tipo!r} nao esta em {sorted(_ENTRY_TYPES)}")
            _num(errs, f"{p}.entrada.agressividade", entrada.get("agressividade"), 0.0, 1.0)
        elif entrada:
            errs.append(f"{p}.entrada: deve ser objeto")

        # saida
        saida = ev.get("saida", {})
        if isinstance(saida, dict):
            pausa = saida.get("pausa", DramaticPause.NONE.value)
            if pausa not in _PAUSES:
                errs.append(f"{p}.saida.pausa: {pausa!r} nao esta em {sorted(_PAUSES)}")
        elif saida:
            errs.append(f"{p}.saida: deve ser objeto")

        # palco
        palco = ev.get("palco", {})
        if isinstance(palco, dict):
            _num(errs, f"{p}.palco.estereo", palco.get("estereo"), -100, 100)
        elif palco:
            errs.append(f"{p}.palco: deve ser objeto")

    if errs:
        raise SchemaError(errs)
