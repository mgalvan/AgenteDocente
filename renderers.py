"""Export the shared internal artifact with the standard backend."""
from image_renderers import export


def artifact_file(artifact, requested_format="", *, best_effort=False, warnings=None):
    fmt=requested_format or artifact.get("format", "pdf")
    if artifact.get('artifact_type') == 'modulogoogle':
        from google_form_export import export_google_form
        if fmt in ('json', 'zip'):
            from quiz_feedback import export_feedback
            return export_feedback(artifact, fmt)
        if fmt == 'gs':
            return export_google_form(artifact)
        if fmt not in ('pdf', 'docx'):
            raise ValueError("Il modulo Google si scarica in PDF, Word o GS.")
        from google_form_export import google_form_document
        return export(google_form_document(artifact), fmt)
    if fmt=='docx' and artifact.get('artifact_type')=='student_test':
        from verification_template import FILE, compile_test
        if FILE.exists():return compile_test(artifact)
    return export(artifact, fmt)
