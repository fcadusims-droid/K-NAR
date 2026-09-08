"""Camada de áudio (DSP): trim de silêncio, reamostragem, voz sintética de rascunho.

Depende de numpy. NÃO é importada na inicialização do pacote — os módulos que a usam
fazem imports tardios, para o núcleo (segmentação/roteiro) seguir sem dependências.
"""
