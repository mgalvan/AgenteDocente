"""Export the shared internal artifact with the standard backend."""
from image_renderers import export


def artifact_file(artifact, requested_format="", *, best_effort=False, warnings=None):
    fmt=requested_format or artifact.get("format", "pdf")
    if fmt=='docx' and artifact.get('artifact_type')=='student_test':
        from verification_template import FILE, compile_test
        if FILE.exists():return compile_test(artifact)
    return export(artifact, fmt)
