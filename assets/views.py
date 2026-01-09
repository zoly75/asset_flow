from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views import generic
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Q
from django.contrib.auth.views import PasswordChangeView
from django.contrib import messages
import qrcode
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from .models import Asset, UserProfile, Employee, User
from .forms import AssetForm, AssignAssetForm, AssetStatusForm, UserProfileForm, EmployeeForm, SignUpForm, UserUpdateForm, TeamUserCreationForm

def get_shared_owner(user):
    """
    Returns the effective owner of the data.
    - If user is a Boss (master_account is None): returns user.
    - If user is a Team Member (master_account is set): returns the Boss.
    """
    if hasattr(user, 'userprofile') and user.userprofile.master_account:
        return user.userprofile.master_account
    return user

def is_boss(user):
    """
    Returns True if the user is the Account Owner (can manage billing/team).
    Returns False if user is just a Team Member.
    """
    if hasattr(user, 'userprofile') and user.userprofile.master_account:
        return False
    return True

@login_required
def dashboard(request):
    """
    Lists assets with Search functionality.
    Only shows assets belonging to the logged-in user.
    """
    # 1. Determine who implies the ownership
    owner = get_shared_owner(request.user)

    # 2. Filter assets by the OWNER (not necessarily owner)
    assets = Asset.objects.filter(owner=owner)

    asset_count = assets.count()

    query = request.GET.get('q') # Get the search term from URL (e.g., ?q=drill)

    if query:
        # Use Q objects for complex "OR" lookups.
        # We search in Name OR Serial OR Description OR Assigned Employee.
        # 'icontains' makes it case-insensitive.
        assets = assets.filter(
            Q(name__icontains=query) | 
            Q(serial_number__icontains=query) |
            Q(description__icontains=query) |
            Q(assigned_to__icontains=query)|
            Q(uuid__icontains=query)
        )

    # 3. Sorting (Always keep the list consistent)
    assets = assets.order_by('name')

    context = {
        'assets': assets,
        'asset_count': asset_count,
        'search_query': query,
        'is_boss': is_boss(request.user)
    }
    return render(request, 'assets/dashboard.html', context)

@login_required
def profile_settings(request):
    """
    Handles TWO forms:
    1. u_form: User data (Email, Name)
    2. p_form: Profile data (Company, Phone)
    """
    user_is_boss = is_boss(request.user)

    if request.method == 'POST':
        # 1. User Form (Available to everyone)
        u_form = UserUpdateForm(request.POST, instance=request.user)
        
        # 2. Profile Form (Company Info - Only for Boss)
        p_form = UserProfileForm(request.POST, instance=request.user.userprofile) if user_is_boss else None

        # Validation Logic:
        # If Boss: Both forms must be valid.
        # If Team Member: Only u_form needs to be valid.
        if u_form.is_valid() and (not user_is_boss or p_form.is_valid()):
            u_form.save()
            
            # Only save company details if user is allowed
            if user_is_boss and p_form:
                p_form.save()            
            
            messages.success(request, 'Your profile has been updated!') # <--- Feedback!
            return redirect('profile_settings')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = UserProfileForm(instance=request.user.userprofile)

    context = {
        'u_form': u_form,
        'p_form': p_form,
        'is_boss': user_is_boss
    }
    return render(request, 'assets/profile_form.html', context)

class CustomPasswordChangeView(PasswordChangeView):
    """
    Custom view to change password.
    Adds a success message and uses a styled template.
    """
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('profile_settings')

    def form_valid(self, form):
        # This adds the green success message
        messages.success(self.request, "Your password has been successfully updated!")
        return super().form_valid(form)

@login_required
def employee_list(request):
    """
    Team Management Page.
    Displays the list of employees with SEARCH functionality.
    """
    owner = get_shared_owner(request.user)
    # Handle "Add New Employee" form submission
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.owner = owner # Link to the current company
            employee.save()
            return redirect('employee_list')
    else:
        form = EmployeeForm()

    # 1. Base Query: Fetch existing employees owned by the user
    employees = Employee.objects.filter(owner=owner).order_by('name')

    # 2. Search Logic (New)
    query = request.GET.get('q') # Get the search term from URL
    if query:
        # Filter by Name OR Email OR Phone
        # (Make sure 'from django.db.models import Q' is at the top of the file)
        employees = employees.filter(
            Q(name__icontains=query) | 
            Q(email__icontains=query) | 
            Q(phone__icontains=query)
        )

    # 3. Calculate Stats
    total_assigned = Asset.objects.filter(owner=owner, status='ASSIGNED').count()

    context = {
        'employees': employees,
        'form': form,
        'total_assigned': total_assigned,
        'search_query': query,
        'is_boss': is_boss(request.user)
    }

    return render(request, 'assets/employee_list.html', context)

@login_required
def delete_employee(request, pk):
    """
    Deletes a team member with confirmation page.
    Releases their assets back to storage (AVAILABLE).
    """
    owner = get_shared_owner(request.user)
    employee = get_object_or_404(Employee, pk=pk, owner=owner)

    if request.method == 'POST':
        # 1. Find assets assigned to this employee
        assigned_assets = Asset.objects.filter(assigned_to=employee)
        
        # 2. BULK UPDATE: Set assigned_to to None AND status to AVAILABLE
        # Using .update() is efficient as it hits the DB once
        assigned_assets.update(assigned_to=None, status='AVAILABLE')

        # 3. Delete the employee record
        employee_name = employee.name
        employee.delete()
        
        messages.success(request, f"{employee_name} has been removed. Their assets have been returned to storage.")
        return redirect('employee_list')

    # Handle GET request: Show confirmation page
    context = {
        'employee': employee,
        'assigned_assets_count': employee.assets.count()
    }
    return render(request, 'assets/delete_employee_confirm.html', context)

@login_required
def add_asset(request):
    # --- START OF LIMIT CHECK ---
    # 1. Count current assets owned by the user
    owner = get_shared_owner(request.user)

    # Limit check on the OWNER's account
    current_count = Asset.objects.filter(owner=owner).count()
    
    # 2. Get limits from UserProfile (handle cases where profile might be missing)
    if hasattr(owner, 'userprofile'):
        limit = owner.userprofile.max_assets
        is_premium = owner.userprofile.is_premium
    else:
        # Fallback defaults if something is wrong with the profile
        limit = 50 
        is_premium = False

    # 3. The Gatekeeper: If limit reached AND not premium -> Block access
    if not is_premium and current_count >= limit:
        messages.warning(request, f"You have reached the limit of the Free Plan ({limit} assets). Please upgrade to add more.")
        return redirect('dashboard')
    # --- END OF LIMIT CHECK ---    

    if request.method == 'POST':
        # PASS USER HERE:
        form = AssetForm(request.POST, user=owner) 
        if form.is_valid():
            asset = form.save(commit=False)
            asset.owner = owner
            
            asset.save()
            return redirect('dashboard')
    else:
        # PASS USER HERE TOO:
        form = AssetForm(user=owner)
    
    return render(request, 'assets/asset_form.html', {'form': form})

def public_asset(request, uuid):
    """
    Publicly accessible view for scanning QR codes.
    NO login required here!
    """
    # 1. Fetch the asset using the secure UUID instead of the simple ID.
    # If the UUID is wrong, it returns a 404 Not Found error.
    asset = get_object_or_404(Asset, uuid=uuid)
    
    # 2. Render a simplified, mobile-friendly template
    return render(request, 'assets/public_asset.html', {'asset': asset})

@login_required
def generate_qr(request, uuid):
    """
    Generates a QR code image on the fly.
    Returns: PNG image bytes.
    """
    owner = get_shared_owner(request.user)
    asset = get_object_or_404(Asset, uuid=uuid, owner=owner) # Security check
    # 1. Construct the full URL that the QR code should point to.
    # request.build_absolute_uri() turns '/asset/...' into 'https://domain.com/asset/...'
    # This is crucial so it works on any domain!
    link = request.build_absolute_uri(f'/asset/{uuid}/')
    
    # 2. Create the QR code object
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=5,
    )
    qr.add_data(link)
    qr.make(fit=True)
    
    # 3. Create an image from the QR code instance
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 4. Save the image into a memory buffer (BytesIO) instead of a file on disk.
    # This is faster and doesn't clutter the server's hard drive.
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    
    # 5. Return the binary data as an HTTP response with correct content type
    return HttpResponse(buffer.getvalue(), content_type="image/png")

@login_required
def edit_asset(request, uuid):
    owner = get_shared_owner(request.user)
    asset = get_object_or_404(Asset, uuid=uuid, owner=owner)

    is_premium = False
    if hasattr(owner, 'userprofile'):
        is_premium = owner.userprofile.is_premium

    if is_premium:
        history = asset.history.all().order_by('-date')
    else:
        history = None
    
    if request.method == 'POST':
        # PASS USER HERE:
        form = AssetForm(request.POST, instance=asset, user=owner)
        if form.is_valid():
            asset = form.save(commit=False)
            asset._current_user = request.user
            asset.save()
            return redirect('dashboard')
    else:
        # PASS USER HERE TOO:
        form = AssetForm(instance=asset, user=owner)

    context = {
        'form': form, 
        'asset': asset,   # We need this to check if we are in 'Edit' mode
        'history': history, # The list of changes
        'is_premium': is_premium
    }

    return render(request, 'assets/asset_form.html', context)

@login_required
def delete_asset(request, uuid):
    """
    Deletes an asset after confirmation.
    """
    owner = get_shared_owner(request.user)
    asset = get_object_or_404(Asset, uuid=uuid, owner=owner)

    if request.method == 'POST':
        # 4. If the user clicked "Confirm Delete" button
        asset.delete()
        return redirect('dashboard')

    # 5. Show a confirmation page before deleting (Safety net)
    return render(request, 'assets/delete_confirm.html', {'asset': asset})

@login_required
def assign_asset(request, uuid):
    """
    Assigns an asset to an employee from the dropdown list.
    """
    owner = get_shared_owner(request.user)
    asset = get_object_or_404(Asset, uuid=uuid, owner=owner)

    if request.method == 'POST':
        # We must pass 'user=owner' to the form for filtering!
        form = AssignAssetForm(request.POST, instance=asset, user=owner)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.status = Asset.STATUS_ASSIGNED
            asset._current_user = request.user
            asset.save()
            return redirect('dashboard')
    else:
        # Pass user here too for the GET request
        form = AssignAssetForm(instance=asset, user=owner)

    return render(request, 'assets/assign_form.html', {'form': form, 'asset': asset})

@login_required
def return_asset(request, uuid):
    """
    One-click action to return an asset to inventory.
    Changed to accept GET requests to avoid nested form issues in the dashboard.
    """
    owner = get_shared_owner(request.user)
    asset = get_object_or_404(Asset, uuid=uuid, owner=owner)
    
    # We removed the "if request.method == 'POST':" check
    # so clicking a simple link works immediately.
    asset.status = Asset.STATUS_AVAILABLE
    asset.assigned_to = None # Clear the name
    asset._current_user = request.user
    asset.save()
        
    return redirect('dashboard')

@login_required
def update_status(request, uuid):
    owner = get_shared_owner(request.user)
    asset = get_object_or_404(Asset, uuid=uuid, owner=owner)

    if request.method == 'POST':
        # We must pass the user to the form to filter the employee dropdown
        form = AssetStatusForm(request.POST, instance=asset, user=owner)
        if form.is_valid():
            asset = form.save(commit=False)
            asset._current_user = request.user
            asset.save()
            return redirect('dashboard')
    else:
        # Pass user in GET request as well to populate the dropdown
        form = AssetStatusForm(instance=asset, user=owner)

    return render(request, 'assets/status_form.html', {'form': form, 'asset': asset})

@login_required
def edit_employee(request, pk):
    """
    Loads the existing 'employee_list' template, 
    but pre-fills the form with the selected employee's data.
    """
    owner = get_shared_owner(request.user)
    # 1. Get the employee we want to edit
    employee_to_edit = get_object_or_404(Employee, pk=pk, owner=owner)

    # 2. Get the full list (so the left side table doesn't disappear!)
    employees = Employee.objects.filter(owner=owner).order_by('name')

    if request.method == 'POST':
        # Create form with INSTANCE (this triggers Update instead of Create)
        form = EmployeeForm(request.POST, instance=employee_to_edit)
        if form.is_valid():
            form.save()
            # After save, go back to clean 'add mode'
            return redirect('employee_list')
    else:
        # Pre-fill form
        form = EmployeeForm(instance=employee_to_edit)

    # Render the SAME template as the main list
    return render(request, 'assets/employee_list.html', {
        'employees': employees, 
        'form': form,
        'editing': True # Flag to show "Cancel" button in template
    })

@login_required
def team_list(request):
    """
    Lists all users who can log in to this account.
    Only accessible by the Boss.
    """
    if not is_boss(request.user):
        return redirect('dashboard')
    
    # Get users who have THIS user as their master_account
    team_members = User.objects.filter(userprofile__master_account=request.user)
    
    return render(request, 'assets/team_list.html', {'team_members': team_members})

@login_required
def add_team_member(request):
    """
    Creates a new LOGIN User linked to the current Boss.
    RESTRICTED TO PREMIUM USERS ONLY.
    """
    if not is_boss(request.user):
        return redirect('dashboard')
    
    # --- PREMIUM CHECK ---
    # Using the new smart property 'effective_premium' to verify status.
    if not request.user.userprofile.effective_premium:
         # Ensure you have the 'premium_lock.html' template ready or redirect to pricing
        return render(request, 'assets/premium_lock.html', {'feature_name': 'Team Access'})

    if request.method == 'POST':
        form = TeamUserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            
            # LINK TO BOSS
            new_user.userprofile.master_account = request.user
            new_user.userprofile.save()
            
            messages.success(request, f"Team member {new_user.username} created!")
            return redirect('team_list')
    else:
        form = TeamUserCreationForm()
    
    return render(request, 'assets/team_form.html', {'form': form})

@login_required
def delete_team_member(request, pk):
    """
    Removes a login user from the team.
    """
    if not is_boss(request.user):
        return redirect('dashboard')
        
    user_to_remove = get_object_or_404(User, pk=pk, userprofile__master_account=request.user)
    
    if request.method == 'POST':
        username = user_to_remove.username
        user_to_remove.delete()
        messages.success(request, f"User {username} removed.")
        return redirect('team_list')
        
    return render(request, 'assets/delete_team_confirm.html', {'member': user_to_remove})

@login_required
def download_labels_pdf(request):
    """
    Generates an A4 PDF with QR labels for ALL assets.
    """
    owner = get_shared_owner(request.user)
    # 1. Setup the PDF Buffer
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # 210mm x 297mm basically

    # Company Name for footer
    try:
        company_name = f"Property of {owner.userprofile.company_name}"
    except:
        company_name = "Property of Asset Manager"
    
    # 2. Define Layout (Grid System)
    # 3 columns, 8 rows = 24 labels per page
    cols = 3
    rows = 8
    
    # Label dimensions (approx 70x37mm is standard for 3x8 sheets)
    label_w = 70 * mm
    label_h = 37 * mm
    
    # Margins to center the grid on A4
    margin_x = (width - (cols * label_w)) / 2
    margin_y = (height - (rows * label_h)) / 2

    # 3. Get Assets
    # Check for SINGLE item (GET param)
    single_uuid = request.GET.get('uuid')
    
    # Check for SELECTED items (POST list)
    selected_ids = request.POST.getlist('asset_ids')

    is_premium = False
    if hasattr(owner, 'userprofile'):
        is_premium = owner.userprofile.is_premium

    if single_uuid:
        # Mode A: Single Asset
        assets = Asset.objects.filter(owner=owner, uuid=single_uuid)
    elif selected_ids:
        # Mode B: Bulk Selection
        if not is_premium and len(selected_ids) > 1:
            return render(request, 'assets/premium_lock.html')

        assets = Asset.objects.filter(owner=owner, uuid__in=selected_ids).order_by('name')
    else:
        # Mode C: Print ALL (Default fallback)
        if not is_premium:
            return render(request, 'assets/premium_lock.html')

        assets = Asset.objects.filter(owner=owner).order_by('name')

    if not assets.exists():
        # If no assets found, redirect back to dashboard
        return redirect('dashboard')   

    # Loop variables
    c = 0 # current column
    r = 0 # current row (starts from bottom in PDF!)
    
    # In ReportLab (0,0) is BOTTOM-LEFT corner.
    # So we need to calculate 'y' from the top down visually.
    start_y = height - margin_y - label_h

    for asset in assets:
        # Calculate X and Y for current label
        x = margin_x + (c * label_w)
        y = start_y - (r * label_h)
        
        # --- DRAWING THE LABEL CONTENT ---
        
        # A. Draw a light border (guide for cutting) - Optional
        p.setStrokeColorRGB(0.8, 0.8, 0.8) # Light grey
        p.rect(x, y, label_w, label_h)
        
        # B. Generate QR Code in memory
        qr_link = request.build_absolute_uri(f'/asset/{asset.uuid}/')
        qr = qrcode.QRCode(box_size=10, border=1) # Minimal border
        qr.add_data(qr_link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to ReportLab readable format
        img_buffer = BytesIO()
        img.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        qr_image = ImageReader(img_buffer)
        
        # Draw QR (Square shape, left side of label)
        qr_size = 25 * mm
        qr_x = x + 2 * mm
        qr_y = y + (label_h - qr_size) / 2
        p.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size)
        
        # --- C. Draw Text (Right side of label) ---
        
        # Calculate X position (Right of the QR code)
        text_x = qr_x + qr_size + 3 * mm
        
        # Start position (Top of the text area)
        # We start a bit higher because we have more lines now
        current_y = y + label_h - 6 * mm 
        
        p.setFillColorRGB(0, 0, 0)
        
        # 1. ASSET NAME (Bold)
        p.setFont("Helvetica-Bold", 10)
        # Truncate if too long (2 lines would be too complex for now)
        display_name = asset.name[:18] + "..." if len(asset.name) > 18 else asset.name
        p.drawString(text_x, current_y, display_name)
        
        # Move down
        current_y -= 4 * mm

        # 2. ID (UUID Short) - Backup if QR fails
        p.setFont("Helvetica", 8)
        # Explanation: taking the first 8 chars of the UUID is usually unique enough
        p.drawString(text_x, current_y, f"ID: {str(asset.uuid)[:8]}")
        
        # Move down gap for Company Info
        current_y -= 5 * mm

        # --- GET PROFILE DATA ---
        try:
            profile = owner.userprofile
            comp_name = profile.company_name
            phone = profile.phone_number
            email = owner.email
        except:
            comp_name, phone, email = "", "", ""

        # 3. COMPANY NAME (if exists)
        if comp_name:
            p.setFont("Helvetica-Oblique", 7)
            p.setFillColorRGB(0.3, 0.3, 0.3) # Dark Grey
            p.drawString(text_x, current_y, comp_name)
            current_y -= 3.5 * mm # Move down

        # 4. PHONE (if exists)
        if phone:
            p.setFont("Helvetica", 6)
            p.setFillColorRGB(0.4, 0.4, 0.4)
            p.drawString(text_x, current_y, f"Tel: {phone}")
            current_y -= 3 * mm # Move down

        # 5. EMAIL (if exists)
        if email:
            p.setFont("Helvetica", 6)
            p.setFillColorRGB(0.4, 0.4, 0.4)
            p.drawString(text_x, current_y, email)
            # No need to move down further
        # --- END DRAWING ---

        # 4. Move to next position
        c += 1
        if c >= cols:
            c = 0
            r += 1
            
        # 5. Check for Page Break
        if r >= rows:
            p.showPage() # Create new page
            c = 0
            r = 0
            
    # 6. Finalize
    p.showPage()
    p.save()
    buffer.seek(0)
    
    return HttpResponse(buffer, content_type='application/pdf')

class SignUpView(generic.CreateView):
    """
    View for public user registration.
    Uses Django's built-in UserCreationForm.
    Redirects to login page upon success.
    """
    form_class = SignUpForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'

def pricing(request):
    return render(request, 'assets/pricing.html')

def help_page(request):
    """
    Renders the Help & Documentation page.
    """
    return render(request, 'assets/help.html')

def terms_of_service(request):
    return render(request, 'assets/terms.html')

def privacy_policy(request):
    return render(request, 'assets/privacy.html')