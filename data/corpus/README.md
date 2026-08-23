# Corpus de repositorios

Snapshot local del material sobre el que trabaja el clasificador. Un directorio
por repositorio, con un `snapshot.json` dentro:

```
data/corpus/
  <slug>/
    snapshot.json
```

El formato lo define `src/btm/system/corpus.py`:

```json
{
  "slug": "acme-pay",
  "name": "acme-pay",
  "description": "Cliente de pagos",
  "captured_at": "2026-08-23",
  "source_url": "https://example.invalid/acme-pay",
  "documents": [
    {
      "url": "https://example.invalid/acme-pay/readme",
      "title": "README",
      "text": "...",
      "kind": "readme"
    }
  ]
}
```

`description` puede ser `null`: el registro de origen no siempre la trae.

## Criterio de selección

Se fija antes de recolectar, y toda ampliación del corpus lo respeta.

- **Cola larga.** Repositorios de baja popularidad, preferentemente recientes.
  El material muy conocido no dice nada sobre la capacidad de leer: el modelo ya
  lo ha visto y responde de memoria.
- **Al menos cinco documentos por snapshot.** Con menos, el material entra
  entero en el contexto y no se ejercita el camino de selección de documentos.
- **Repositorios con descripción y sin ella, en proporción parecida.** Los dos
  casos existen en el registro de origen y el clasificador tiene que resolver
  ambos; un corpus donde casi todos traen descripción no dice cómo se comporta
  con los que no.
- **Fecha de captura y URL de origen en cada snapshot**, en los campos
  `captured_at` y `source_url`.

## Versionado

El corpus se versiona en el repositorio. Los resultados guardados apuntan a un
estado concreto del corpus: reemplazar o reescribir un snapshot invalida la
comparación con lo ya registrado. Para corregir una captura, añadir una nueva en
lugar de editar la existente.
