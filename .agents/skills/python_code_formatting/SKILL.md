---
name: Python Code Formatting
description: A skill to format and organize Python code using the Black formatter and Ruff linter.
---

# Python Code Formatting Skill

This skill provides the standard workflow for organizing, formatting, and linting Python code to ensure strict adherence to PEP 8 guidelines, `black` formatter, and `ruff` linter as per project configurations.

## Prerequisites

Ensure that both `black` and `ruff` are installed in your environment:
```bash
pip install black ruff
```

## Workflow

When tasked with formatting or organizing Python files, follow these exact steps:

### 1. Format Code using Black
Run the `black` code formatter on the target file or directory. This will automatically format the code strictly to standard conventions.
```bash
black <path_to_file_or_directory>
```

### 2. Lint and Organize Imports using Ruff
Run `ruff` to act as the linter and import organizer. Standard guidelines dictate grouping imports into: Standard Library > Third Party > Local Application, and using absolute imports. `ruff` can automatically fix import ordering and various linting issues.
```bash
ruff check --fix <path_to_file_or_directory>
```
If you specifically want to only format/organize the imports via ruff:
```bash
ruff check --select I --fix <path_to_file_or_directory>
```

### 3. Review Code Structure
Ensure the following naming conventions and basic formatting configurations hold true:
- Variables/Functions: `snake_case`
- Classes: `PascalCase`
- Constants: `SCREAMING_SNAKE_CASE`
- Protected/Private: `_leading_underscore`
- Type Hinting must be present for all function signatures and class attributes.
- F-Strings should be used for string interpolation.

If any manual refactoring is needed that `black` or `ruff` could not automatically resolve, perform it directly, adhering strictly to the user's defined Python constraints.
