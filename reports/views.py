from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import Report, RapportHeader, RapportResultat
from .forms import ReportForm, ProfilForm
from .extractor import extract_rapport

User = get_user_model()


def _run_extraction(report: Report) -> None:
    """
    Lance l'extraction PDF et persiste les données dans :
        - RapportHeader   (Partie 1 — champs entête)
        - RapportResultat (Partie 2 — lignes du tableau résultats)
    Met à jour report.status et report.processed_text.
    """
    report.status = 'PROCESSING'
    report.save(update_fields=['status'])

    try:
        pdf_path = report.file.path
        data = extract_rapport(pdf_path)

        # --- Partie 1 : créer RapportHeader ---
        RapportHeader.objects.filter(report=report).delete()
        header_obj = RapportHeader.objects.create(
            report=report,
            **data['header']
        )

        # --- Partie 2 : créer les lignes RapportResultat ---
        RapportResultat.objects.filter(header=header_obj).delete()
        for row in data['resultats']:
            RapportResultat.objects.create(
                header=header_obj,
                essai=row['essai'],
                resultat=row['resultat'],
                unite=row['unite'],
            )

        report.processed_text = data['raw_text']
        report.status = 'COMPLETED'
        report.save(update_fields=['processed_text', 'status'])

    except Exception as e:
        report.status = 'FAILED'
        report.processed_text = f"Erreur extraction : {e}"
        report.save(update_fields=['processed_text', 'status'])


@login_required
def dashboard(request):
    if request.user.role == 'admin':
        reports = Report.objects.all().order_by('-uploaded_at')
        completed_count = reports.filter(status='COMPLETED').count()
        pending_count = reports.filter(status='PENDING').count()
        refused_count = reports.filter(status='REFUSED').count()
        users_count = User.objects.filter(role='user').count()

        # --- Filtrage admin (recherche + statut) ---
        q = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        if q:
            reports = reports.filter(
                Q(title__icontains=q) | Q(user__nom__icontains=q)
            )
        if status_filter:
            reports = reports.filter(status=status_filter)

        return render(request, 'reports/dashboard.html', {
            'reports': reports,
            'completed_count': completed_count,
            'pending_count': pending_count,
            'refused_count': refused_count,
            'users_count': users_count,
            'is_admin': True,
            'search_query': q,
            'status_filter': status_filter,
        })
    else:
        reports = Report.objects.filter(user=request.user).order_by('-uploaded_at')
        completed_count = reports.filter(status='COMPLETED').count()
        pending_count = reports.filter(status='PENDING').count()
        refused_count = reports.filter(status='REFUSED').count()
        return render(request, 'reports/dashboard.html', {
            'reports': reports,
            'completed_count': completed_count,
            'pending_count': pending_count,
            'refused_count': refused_count,
            'is_admin': False,
        })

@login_required
def upload_report(request):
    if request.method == 'POST':
        form = ReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.user = request.user
            # Scénario A : extraction directe / Scénario B : envoi à l'admin
            extract_now = request.POST.get('extract_now') == '1'
            if extract_now:
                report.save()
                _run_extraction(report)
            else:
                report.status = 'PENDING'
                report.save()
            return redirect('reports:dashboard')
    else:
        form = ReportForm()
    return render(request, 'reports/upload.html', {'form': form})

@login_required
def history(request):
    if request.user.role == 'admin':
        reports = Report.objects.all().order_by('-uploaded_at')
    else:
        reports = Report.objects.filter(user=request.user).order_by('-uploaded_at')
    return render(request, 'reports/history.html', {'reports': reports})

@login_required
def delete_report(request, pk):
    if request.user.role == 'admin':
        report = get_object_or_404(Report, pk=pk)
    else:
        report = get_object_or_404(Report, pk=pk, user=request.user)
    if request.method == 'POST':
        report.delete()
        return redirect('reports:dashboard')
    return redirect('reports:dashboard')

@login_required
def approve_report(request, pk):
    """Admin approuve un rapport en attente → lance l'extraction."""
    if request.user.role != 'admin' or request.method != 'POST':
        return redirect('reports:dashboard')
    report = get_object_or_404(Report, pk=pk, status='PENDING')
    _run_extraction(report)
    return redirect('reports:dashboard')


@login_required
def refuse_report(request, pk):
    """Admin refuse un rapport en attente."""
    if request.user.role != 'admin' or request.method != 'POST':
        return redirect('reports:dashboard')
    report = get_object_or_404(Report, pk=pk, status='PENDING')
    report.status = 'REFUSED'
    report.save(update_fields=['status'])
    return redirect('reports:dashboard')


@login_required
def manage_users(request):
    if request.user.role != 'admin':
        return redirect('reports:dashboard')
    users = User.objects.filter(role='user')
    return render(request, 'reports/manage_users.html', {'users': users})

@login_required
def profil(request):
    if request.method == 'POST':
        form = ProfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('reports:profil')
    else:
        form = ProfilForm(instance=request.user)
    return render(request, 'reports/profil.html', {
        'form': form,
        'is_admin': request.user.role == 'admin',
    })

