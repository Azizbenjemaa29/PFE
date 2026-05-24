import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST
from .models import Report, RapportHeader, RapportResultat
from .forms import ReportForm, ProfilForm, AdminChangePasswordForm
from .extractor import extract_rapport

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB
MAX_FILES_PER_BATCH = 10
ALLOWED_EXTENSIONS = {'.pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
ALLOWED_UPLOAD_EXTENSIONS = ALLOWED_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS

User = get_user_model()


def _run_extraction(report: Report) -> None:
    report.status = 'PROCESSING'
    report.save(update_fields=['status'])
    try:
        pdf_path = report.file.path
        data = extract_rapport(pdf_path)
        RapportHeader.objects.filter(report=report).delete()
        header_obj = RapportHeader.objects.create(report=report, **data['header'])
        RapportResultat.objects.filter(header=header_obj).delete()
        for row in data['resultats']:
            RapportResultat.objects.create(
                header=header_obj,
                essai=row['essai'],
                methode_essai=row.get('methode_essai', ''),
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
@xframe_options_exempt
def serve_pdf(request, pk):
    report = get_object_or_404(Report, pk=pk)
    if request.user.role != 'admin' and report.user != request.user:
        raise Http404
    try:
        response = FileResponse(open(report.file.path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{report.filename()}"'
        return response
    except FileNotFoundError:
        raise Http404


@login_required
def dashboard(request):
    if request.user.role == 'admin':
        reports = Report.objects.filter(is_deleted=False).order_by('-uploaded_at')
        completed_count = reports.filter(status='COMPLETED').count()
        pending_count = reports.filter(status='PENDING').count()
        processing_count = reports.filter(status='PROCESSING').count()
        refused_count = reports.filter(status='REFUSED').count()
        users_count = User.objects.filter(role='user').count()

        q = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()
        if q:
            reports = reports.filter(Q(title__icontains=q) | Q(user__nom__icontains=q))
        if status_filter:
            reports = reports.filter(status=status_filter)

        return render(request, 'reports/dashboard.html', {
            'reports': reports,
            'completed_count': completed_count,
            'pending_count': pending_count,
            'processing_count': processing_count,
            'refused_count': refused_count,
            'users_count': users_count,
            'is_admin': True,
            'search_query': q,
            'status_filter': status_filter,
            'active_page': 'dashboard',
        })
    else:
        reports = Report.objects.filter(user=request.user, is_deleted=False).order_by('-uploaded_at')
        completed_count = reports.filter(status='COMPLETED').count()
        pending_count = reports.filter(status='PENDING').count()
        processing_count = reports.filter(status='PROCESSING').count()
        refused_count = reports.filter(status='REFUSED').count()
        return render(request, 'reports/dashboard.html', {
            'reports': reports,
            'completed_count': completed_count,
            'pending_count': pending_count,
            'processing_count': processing_count,
            'refused_count': refused_count,
            'is_admin': False,
            'active_page': 'dashboard',
        })


@login_required
def upload_report(request):
    if request.method == 'POST':
        files = request.FILES.getlist('file')
        title = (request.POST.get('title') or '').strip()
        extract_now = request.POST.get('extract_now') == '1'

        if not title:
            messages.error(request, "Le titre du rapport est obligatoire.")
            return redirect('reports:upload_report')
        if not files:
            messages.error(request, "Veuillez sélectionner au moins un fichier.")
            return redirect('reports:upload_report')
        if len(files) > MAX_FILES_PER_BATCH:
            messages.error(request, f"Maximum {MAX_FILES_PER_BATCH} fichiers par lot ({len(files)} soumis).")
            return redirect('reports:upload_report')

        success_count = 0
        fail_count = 0
        multi = len(files) > 1

        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in ALLOWED_UPLOAD_EXTENSIONS:
                messages.error(request, f"{f.name} : formats acceptés — PDF, JPG, PNG, GIF, WebP.")
                fail_count += 1
                continue
            if f.size > MAX_UPLOAD_SIZE:
                messages.error(request, f"{f.name} : fichier trop volumineux (max 25 MB).")
                fail_count += 1
                continue

            report_title = f"{title} — {f.name}" if multi else title
            try:
                report = Report(title=report_title, file=f, user=request.user)
                if extract_now:
                    report.save()
                    _run_extraction(report)
                else:
                    report.status = 'PENDING'
                    report.save()
                success_count += 1
            except Exception as e:
                fail_count += 1
                messages.error(request, f"{f.name} : échec ({e}).")

        if success_count and not fail_count:
            messages.success(request, f"{success_count} rapport(s) téléchargé(s) avec succès.")
        elif success_count and fail_count:
            messages.warning(request, f"{success_count} réussi(s), {fail_count} échec(s).")
        return redirect(reverse('reports:dashboard') + '?uploaded=1')

    form = ReportForm()
    return render(request, 'reports/upload.html', {
        'form': form,
        'active_page': 'upload',
        'is_admin': request.user.role == 'admin',
    })


@login_required
def history(request):
    if request.user.role == 'admin':
        reports = Report.objects.filter(is_deleted=False).order_by('-uploaded_at')
    else:
        reports = Report.objects.filter(user=request.user, is_deleted=False).order_by('-uploaded_at')

    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    if q:
        reports = reports.filter(Q(title__icontains=q))
    if status_filter:
        reports = reports.filter(status=status_filter)

    return render(request, 'reports/history.html', {
        'reports': reports,
        'is_admin': request.user.role == 'admin',
        'search_query': q,
        'status_filter': status_filter,
        'active_page': 'history',
    })


@login_required
def report_detail_json(request, pk):
    report = get_object_or_404(Report, pk=pk)
    if request.user.role != 'admin' and report.user != request.user:
        raise Http404
    try:
        header = report.header
        resultats = list(header.resultats.values('essai', 'methode_essai', 'resultat', 'unite'))
        return JsonResponse({
            'title': report.title,
            'filename': report.filename(),
            'uploaded_at': report.uploaded_at.strftime('%d/%m/%Y %H:%M'),
            'header': {
                'client': header.client,
                'date_emission': header.date_emission or '',
                'ose': header.ose,
                'code': header.code,
                'bon_de_commande': header.bon_de_commande,
                'nature_echantillon': header.nature_echantillon,
                'transport_par': header.transport_par,
                'date_prelevement': str(header.date_prelevement) if header.date_prelevement else '',
                'date_reception': str(header.date_reception) if header.date_reception else '',
                'date_debut_essais': str(header.date_debut_essais) if header.date_debut_essais else '',
                'responsable_laboratoire': header.responsable_laboratoire,
            },
            'resultats': resultats,
        })
    except RapportHeader.DoesNotExist:
        return JsonResponse({'error': 'Données extraites non disponibles.'}, status=404)


@login_required
def delete_report(request, pk):
    if request.user.role == 'admin':
        report = get_object_or_404(Report, pk=pk)
    else:
        report = get_object_or_404(Report, pk=pk, user=request.user)
    if request.method == 'POST':
        try:
            header = report.header
            header.is_deleted = True
            header.save(update_fields=['is_deleted'])
            header.resultats.all().update(is_deleted=True)
        except RapportHeader.DoesNotExist:
            pass
        report.is_deleted = True
        report.save(update_fields=['is_deleted'])
    return redirect('reports:dashboard')


@login_required
def approve_report(request, pk):
    if request.user.role != 'admin' or request.method != 'POST':
        return redirect('reports:dashboard')
    report = get_object_or_404(Report, pk=pk, status='PENDING')
    _run_extraction(report)
    return redirect('reports:dashboard')


@login_required
def refuse_report(request, pk):
    if request.user.role != 'admin' or request.method != 'POST':
        return redirect('reports:dashboard')
    report = get_object_or_404(Report, pk=pk, status='PENDING')
    report.status = 'REFUSED'
    report.save(update_fields=['status'])
    return redirect('reports:dashboard')


@login_required
def powerbi_dashboard(request):
    if request.user.role != 'admin':
        return redirect('reports:dashboard')
    return render(request, 'reports/powerbi_dashboard.html', {
        'is_admin': True,
        'active_page': 'powerbi',
    })


@login_required
def manage_users(request):
    if request.user.role != 'admin':
        return redirect('reports:dashboard')
    users = User.objects.filter(role='user').order_by('nom')
    filiales = users.values_list('filiale', flat=True).distinct()
    return render(request, 'reports/manage_users.html', {
        'users': users,
        'filiales': filiales,
        'is_admin': True,
        'active_page': 'manage_users',
    })


@login_required
def change_user_password(request, pk):
    if request.user.role != 'admin':
        return redirect('reports:dashboard')
    target_user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = AdminChangePasswordForm(request.POST)
        if form.is_valid():
            target_user.set_password(form.cleaned_data['password1'])
            target_user.save()
            messages.success(request, f"Mot de passe de {target_user.nom} modifié avec succès.")
            return redirect('reports:manage_users')
        else:
            for error in form.errors.values():
                messages.error(request, error[0])
            return redirect('reports:manage_users')
    return redirect('reports:manage_users')


@login_required
def profil(request):
    if request.method == 'POST':
        form = ProfilForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            # Validate avatar file if provided
            avatar = request.FILES.get('avatar')
            if avatar:
                ext = os.path.splitext(avatar.name)[1].lower()
                if ext not in ALLOWED_IMAGE_EXTENSIONS:
                    messages.error(request, "Format d'image non supporté. Utilisez JPG, PNG, GIF ou WebP.")
                    return redirect('reports:profil')
                if avatar.size > 5 * 1024 * 1024:
                    messages.error(request, "L'image ne doit pas dépasser 5 MB.")
                    return redirect('reports:profil')
            form.save()
            messages.success(request, "Profil mis à jour avec succès.")
            return redirect('reports:profil')
    else:
        form = ProfilForm(instance=request.user)
    return render(request, 'reports/profil.html', {
        'form': form,
        'is_admin': request.user.role == 'admin',
        'active_page': 'profil',
    })
