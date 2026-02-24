# Contributing to Rynxs

Thank you for your interest in contributing to Rynxs. This document provides guidelines for contributing to the project.

## Code of Conduct

This project adheres to a code of conduct that all contributors are expected to follow:

- Be respectful and inclusive
- Focus on technical merit
- Provide constructive feedback
- Accept constructive criticism

## How to Contribute

### Reporting Issues

Before creating an issue:
- Search existing issues to avoid duplicates
- Use the issue template if provided
- Include steps to reproduce for bugs
- Include environment details (Kubernetes version, CNI, etc.)

### Proposing Features

For new features:
- Open an issue first to discuss the feature
- Explain the use case and benefits
- Consider backwards compatibility
- Wait for maintainer feedback before implementing

### Development Workflow

1. Fork the repository
2. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes
4. Write tests for new functionality
5. Ensure all tests pass
6. Update documentation as needed
7. Commit with conventional commit messages
8. Push to your fork
9. Open a Pull Request

### Branch Naming Convention

Use descriptive branch names:
- `feature/task-queue-system`
- `fix/operator-crash-on-startup`
- `docs/improve-deployment-guide`
- `refactor/cleanup-reconcile-logic`

### Commit Message Format

Follow conventional commits:

```
type(scope): subject

body (optional)

footer (optional)
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements

Examples:
```
feat(operator): add task queue controller

Implement task assignment logic with priority-based scheduling.
Auto-assign tasks to available agents based on zone membership.

Closes #123

---

fix(runtime): prevent race condition in memory snapshot

Add mutex lock around bucket write operations to prevent
concurrent snapshot creation.

---

docs(api): document Task CRD fields

Add complete field reference for Task resource spec and status.
```

### Code Standards

#### Python

- Follow PEP 8
- Use type hints where possible
- Write docstrings for public functions
- Maximum line length: 100 characters
- Use `black` for formatting
- Use `flake8` for linting
- Use `mypy` for type checking

Example:
```python
def reconcile_task(
    task_name: str,
    namespace: str,
    spec: dict,
    logger: logging.Logger
) -> None:
    """Reconcile task assignment and execution.

    Args:
        task_name: Name of the task resource
        namespace: Kubernetes namespace
        spec: Task specification
        logger: Logger instance

    Raises:
        ValueError: If spec is invalid
    """
    pass
```

#### YAML/Kubernetes Manifests

- Use 2-space indentation
- Keep lines under 80 characters where possible
- Use comments for complex configurations
- Validate with `kubectl apply --dry-run`

#### Documentation

- Use clear, concise language
- Include code examples
- Update relevant docs with code changes
- Keep README.md up to date

### Testing

All contributions must include tests:

#### Unit Tests

```bash
cd operator
pytest tests/unit/

cd agent-runtime
pytest tests/unit/
```

#### Integration Tests

```bash
pytest tests/integration/
```

#### E2E Tests

```bash
./scripts/e2e-test.sh
```

### Pull Request Process

1. Ensure your branch is up to date with `main`
2. Rebase if necessary (avoid merge commits)
3. All CI checks must pass
4. Request review from maintainers
5. Address review feedback
6. Maintainer will merge when approved

### Pull Request Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
How has this been tested?

## Checklist
- [ ] Code follows project style
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
- [ ] Commit messages follow convention
```

## Development Setup

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for detailed setup instructions.

Quick start:
```bash
# Clone repository
git clone https://github.com/Uhudsavasindankacanokcu2/rynxs-agentos.git
cd rynxs-agentos

# Install dependencies
cd operator && pip install -r requirements.txt
cd ../agent-runtime && pip install -r requirements.txt

# Create local cluster
kind create cluster --name rynxs-dev

# Install CRDs and base
kubectl apply -f crds/
kubectl apply -k deploy/kustomize/base
```

## Project Structure

```
rynxs-agentos/
├── operator/           # Kubernetes operator
├── agent-runtime/      # Agent execution runtime
├── crds/              # Custom Resource Definitions
├── deploy/            # Deployment manifests
├── helm/              # Helm chart
├── docs/              # Documentation
└── tests/             # Test suites
```

## Getting Help

- GitHub Issues: Bug reports and feature requests
- GitHub Discussions: Questions and community support
- Documentation: Check docs/ directory

## License

By contributing to Rynxs, you agree that your contributions will be licensed under the Apache License 2.0.

## Recognition

Contributors will be recognized in:
- Release notes
- CONTRIBUTORS.md file
- Git commit history

Thank you for contributing to Rynxs!
