# RAG y proyectos

Indexa una carpeta de texto con `voz-codex index mi-proyecto /ruta`. El índice usa SQLite FTS5, divide documentos en fragmentos pequeños y mantiene la fuente de cada resultado. La siguiente etapa añade adaptadores de bases SQLite en solo lectura y las herramientas MCP `search_context` y `project_status`.
