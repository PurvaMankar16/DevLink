import logging

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from core.services import get_client_ip, log_audit_event
from opportunities.models import Connection

from .models import LoginEvent, Profile
from .selectors import get_user_profile_stats, get_user_top_skills
from .services import create_user

logger = logging.getLogger('devlink')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        try:
            user = create_user(username=username, email=email, password=password)
            user.is_active = True
            user.save(update_fields=['is_active'])
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('accounts:signup')

        try:
            from .tasks import send_activation_email
            send_activation_email.delay(user.id)
        except Exception as e:
            logger.warning(f"Async email notification skipped: {e}")

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, f"Welcome to DevLink, {user.username}!")
        return redirect('dashboard:dashboard')

    return render(request, "signup.html")


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def activate_account(request, uidb64: str, token: str):
    """Handle the activation link clicked from the verification email."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=['is_active'])
        log_audit_event('account_activated', request=request, user=user)
        messages.success(request, "Your account has been activated. You can now log in.")
        return redirect('accounts:login')

    # Token invalid or expired
    return render(request, 'accounts/activation_result.html', {'success': False})


def resend_activation(request):
    """Allow a user to request a new activation email."""
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        try:
            user = User.objects.get(email=email, is_active=False)
            try:
                from .tasks import send_activation_email
                send_activation_email.delay(user.id)
            except Exception as e:
                logger.warning(f"Async email notification skipped: {e}")
        except User.DoesNotExist:
            pass  # prevent email enumeration
        messages.info(request, "If that email is registered, a new activation link has been sent.")
        return redirect('accounts:login')
    return render(request, 'accounts/resend_activation.html')


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

def logout_view(request):
    log_audit_event('logout', request=request, user=request.user)
    logout(request)
    return redirect('accounts:login')


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

def forgot_password_view(request):
    """Step 1: user submits their email."""
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        try:
            from .tasks import send_password_reset_email
            send_password_reset_email.delay(email)
        except Exception as e:
            logger.warning(f"Async password reset email skipped: {e}")
        messages.info(
            request,
            "If that email is registered, a password reset link has been sent."
        )
        return redirect('accounts:login')
    return render(request, 'accounts/forgot_password.html')


def reset_password_confirm(request, uidb64: str, token: str):
    """Step 2: user clicks the link and sets a new password."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        messages.error(request, "This password reset link is invalid or has expired.")
        return render(request, 'accounts/password_reset_confirm.html', {'valid_link': False})

    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            # Invalidate all sessions after password change
            update_session_auth_hash(request, user)
            request.session.flush()
            log_audit_event('password_reset', request=request, user=user)
            messages.success(request, "Password updated successfully. Please log in.")
            return redirect('accounts:login')
    else:
        form = SetPasswordForm(user)

    return render(request, 'accounts/password_reset_confirm.html', {
        'form': form,
        'valid_link': True,
        'uidb64': uidb64,
        'token': token,
    })


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def profile_view(request, username):
    user = get_object_or_404(User, username=username)
    profile = Profile.objects.get_or_create(user=user)[0]

    stats = get_user_profile_stats(user)
    top_skills = get_user_top_skills(user)

    is_connected = False
    if request.user.is_authenticated and request.user != user:
        is_connected = (
            Connection.objects.filter(user1=request.user, user2=user).exists()
            or Connection.objects.filter(user1=user, user2=request.user).exists()
        )

    # Reputation data
    try:
        from reputation.selectors import get_user_badges, get_reputation_history
        from reputation.services import get_user_level
        badges = get_user_badges(user)
        level = get_user_level(user)
        reputation_history = get_reputation_history(user, limit=10)
    except Exception:
        badges = []
        level = 'Beginner'
        reputation_history = []

    # Calculate user rank based on reputation_score
    higher_rep_count = Profile.objects.filter(reputation_score__gt=profile.reputation_score).count()
    rank = higher_rep_count + 1

    # Numeric level calculation
    score = profile.reputation_score
    if score >= 3000:
        level_num = 6
    elif score >= 1500:
        level_num = 5
    elif score >= 700:
        level_num = 4
    elif score >= 300:
        level_num = 3
    elif score >= 100:
        level_num = 2
    else:
        level_num = 1

    # Recent Opportunities posted by user
    try:
        from opportunities.models import Opportunity
        recent_opportunities = Opportunity.objects.filter(user=user).order_by('-created_at')[:5]
    except Exception:
        recent_opportunities = []

    # Extract clean list of skill names
    skills_list = []
    if top_skills:
        skills_list = [s[0] if isinstance(s, (list, tuple)) else str(s) for s in top_skills]
    elif profile.skills:
        skills_list = [s.strip() for s in profile.skills.split(',') if s.strip()]
    elif profile.tech_stack:
        skills_list = [s.strip() for s in profile.tech_stack.split(',') if s.strip()]

    return render(request, 'profile.html', {
        'profile_user': user,
        'profile': profile,
        'solutions': stats['solutions'],
        'problems': stats['problems'],
        'total_solutions': stats['total_solutions'],
        'accepted_solutions': stats['accepted_solutions'],
        'total_votes': stats['total_votes'],
        'top_skills': skills_list,
        'is_connected': is_connected,
        'badges': badges,
        'level': level,
        'level_num': level_num,
        'rank': rank,
        'reputation_history': reputation_history,
        'recent_opportunities': recent_opportunities,
    })


@login_required
def my_profile(request):
    return redirect('accounts:profile', username=request.user.username)


@login_required
def edit_profile(request):
    user = request.user
    profile = Profile.objects.get_or_create(user=user)[0]

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        bio = request.POST.get("bio", "")
        github = request.POST.get("github", "")
        linkedin = request.POST.get("linkedin", "")
        profile_image = request.FILES.get("profile_image")

        job_title = request.POST.get("job_title", "").strip()
        location = request.POST.get("location", "").strip()
        skills = request.POST.get("skills", "").strip()

        if User.objects.exclude(id=user.id).filter(username=username).exists():
            messages.error(request, "Username already taken")
            return redirect('accounts:edit_profile')

        user.username = username
        user.email = email
        user.save()

        profile.bio = bio
        profile.github = github
        profile.linkedin = linkedin
        profile.job_title = job_title
        profile.location = location
        profile.skills = skills
        profile.tech_stack = skills
        if profile_image:
            profile.profile_image = profile_image
        profile.save()

        return redirect('accounts:profile', username=user.username)

    return render(request, "edit_profile.html", {"user": user, "profile": profile})


# ---------------------------------------------------------------------------
# Security / Login History
# ---------------------------------------------------------------------------

@login_required
def security_view(request):
    """Show login history and allow session revocation."""
    login_events = LoginEvent.objects.filter(user=request.user)[:20]
    current_session = request.session.session_key
    return render(request, 'accounts/security.html', {
        'login_events': login_events,
        'current_session': current_session,
    })


@login_required
def revoke_session(request, session_key: str):
    """Revoke a specific session by its key."""
    if request.method == "POST":
        from django.contrib.sessions.models import Session
        try:
            session = Session.objects.get(session_key=session_key)
            if session_key == request.session.session_key:
                messages.warning(request, "You cannot revoke your current session here.")
            else:
                session.delete()
                messages.success(request, "Session revoked.")
        except Session.DoesNotExist:
            messages.info(request, "Session not found or already expired.")
    return redirect('accounts:security')
