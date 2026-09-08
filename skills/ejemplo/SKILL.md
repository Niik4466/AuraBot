---
name: ejemplo
description: Skill de ejemplo que muestra el formato de Agent Skills y sirve de plantilla para crear skills propias de AuraBot.
---

# Skill de Ejemplo

Esta carpeta demuestra el formato de las skills de AuraBot, compatible con el
estándar Agent Skills (agentskills.io).

## Estructura

- Cada skill vive en su propia carpeta dentro de `skills/`.
- El archivo `SKILL.md` contiene el frontmatter YAML y las instrucciones.
- El `name` del frontmatter debe coincidir con el nombre de la carpeta.

## Cuándo aplicar esta skill

Cuando el usuario pida ayuda para crear una skill nueva o pregunte cómo
funciona el sistema de skills del bot.

## Instrucciones

1. Explica que una skill es un archivo `SKILL.md` con frontmatter YAML.
2. El frontmatter requiere dos campos:
   - `name`: identificador único en minúsculas con guiones.
   - `description`: descripción de qué hace la skill y cuándo usarla.
3. El cuerpo en markdown son las instrucciones que el modelo seguirá cuando
   la skill esté activa.
4. Recuerda al usuario que puede activar su skill con `/skills load <nombre>`
   y verla con `/skills view <nombre>`.

## Buenas prácticas

- Descripciones claras y específicas: el modelo las usa para decidir cuándo
  aplicar la skill.
- Instrucciones concisas y orientadas a tareas.
- Una skill = un propósito.
