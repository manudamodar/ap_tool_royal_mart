from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .tasks import sync_due_reports_task


@csrf_exempt
def sync_bills(request):
    """Fetch the latest bills from GoFrugal and synchronize the local bill table."""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if not getattr(settings, 'EXTERNAL_GETBILLS_URL', '').strip():
        return JsonResponse({"error": "GoFrugal GetBills API is not configured."}, status=503)
    if not getattr(settings, 'EXTERNAL_GETBILLS_TOKEN', '').strip():
        return JsonResponse({"error": "GoFrugal X-Auth-Token is not configured."}, status=503)

    fin_year = (request.GET.get('finYear') or '').strip()
    if not fin_year:
        return JsonResponse({
            "error": "finYear query parameter is required (for example: 2026_2027).",
        }, status=400)

    task = sync_due_reports_task.delay(fin_year=fin_year)
    return JsonResponse({
        "status": "accepted",
        "message": "Due-report synchronization was queued in the background.",
        "task_id": task.id,
        "fin_year": fin_year,
    }, status=202)
