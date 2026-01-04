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
from .models import Asset, UserProfile, Employee
from .forms import AssetForm, AssignAssetForm, AssetStatusForm, UserProfileForm, EmployeeForm, SignUpForm, UserUpdateForm

@login_required
def dashboard(request):
    """
    Lists assets with Search functionality.
    Only shows assets belonging to the logged-in user.
    """
    # 1. Base Query: Fetch only the user's assets (SAAS Security)
    assets = Asset.objects.filter(owner=request.user)

    # 2. Search Logic
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
        'search_query': query # Pass back to template to keep the input filled
    }
    return render(request, 'assets/dashboard.html', context)

@login_required
def profile_settings(request):
    """
    Handles TWO forms:
    1. u_form: User data (Email, Name)
    2. p_form: Profile data (Company, Phone)
    """
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = UserProfileForm(request.POST, instance=request.user.userprofile)

        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, 'Your profile has been updated!') # <--- Feedback!
            return redirect('profile_settings')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = UserProfileForm(instance=request.user.userprofile)

    context = {
        'u_form': u_form,
        'p_form': p_form
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
    Displays the list of employees and a form to add a new one.
    """
    # Handle "Add New Employee" form submission
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.owner = request.user # Link to the current company
            employee.save()
            return redirect('employee_list')
    else:
        form = EmployeeForm()

    # Fetch existing employees
    employees = Employee.objects.filter(owner=request.user).order_by('name')

    return render(request, 'assets/employee_list.html', {'employees': employees, 'form': form})

@login_required
def delete_employee(request, pk):
    """
    Deletes a team member.
    """
    employee = get_object_or_404(Employee, pk=pk, owner=request.user)

    if request.method == 'POST':
        employee.delete()
        # Note: Assets assigned to this person will have 'assigned_to' set to NULL automatically
        return redirect('employee_list')

    return redirect('employee_list')

@login_required
def add_asset(request):
    if request.method == 'POST':
        # PASS USER HERE:
        form = AssetForm(request.POST, user=request.user) 
        if form.is_valid():
            asset = form.save(commit=False)
            asset.owner = request.user
            
            asset.save()
            return redirect('dashboard')
    else:
        # PASS USER HERE TOO:
        form = AssetForm(user=request.user)
    
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

def generate_qr(request, uuid):
    """
    Generates a QR code image on the fly.
    Returns: PNG image bytes.
    """
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
    asset = get_object_or_404(Asset, uuid=uuid, owner=request.user)
    
    if request.method == 'POST':
        # PASS USER HERE:
        form = AssetForm(request.POST, instance=asset, user=request.user)
        if form.is_valid():
            asset.save()
            return redirect('dashboard')
    else:
        # PASS USER HERE TOO:
        form = AssetForm(instance=asset, user=request.user)
        
    return render(request, 'assets/asset_form.html', {'form': form})

@login_required
def delete_asset(request, uuid):
    """
    Deletes an asset after confirmation.
    """
    asset = get_object_or_404(Asset, uuid=uuid, owner=request.user)

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
    asset = get_object_or_404(Asset, uuid=uuid, owner=request.user)

    if request.method == 'POST':
        # We must pass 'user=request.user' to the form for filtering!
        form = AssignAssetForm(request.POST, instance=asset, user=request.user)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.status = Asset.STATUS_ASSIGNED
            asset.save()
            return redirect('dashboard')
    else:
        # Pass user here too for the GET request
        form = AssignAssetForm(instance=asset, user=request.user)

    return render(request, 'assets/assign_form.html', {'form': form, 'asset': asset})

@login_required
def return_asset(request, uuid):
    """
    One-click action to return an asset to inventory.
    Changed to accept GET requests to avoid nested form issues in the dashboard.
    """
    asset = get_object_or_404(Asset, uuid=uuid, owner=request.user)
    
    # We removed the "if request.method == 'POST':" check
    # so clicking a simple link works immediately.
    asset.status = Asset.STATUS_AVAILABLE
    asset.assigned_to = None # Clear the name
    asset.save()
        
    return redirect('dashboard')

@login_required
def update_status(request, uuid):
    asset = get_object_or_404(Asset, uuid=uuid, owner=request.user)
    
    if request.method == 'POST':
        # We must pass the user to the form to filter the employee dropdown
        form = AssetStatusForm(request.POST, instance=asset, user=request.user)
        if form.is_valid():
            asset.save()
            return redirect('dashboard')
    else:
        # Pass user in GET request as well to populate the dropdown
        form = AssetStatusForm(instance=asset, user=request.user)
        
    return render(request, 'assets/status_form.html', {'form': form, 'asset': asset})

@login_required
def edit_employee(request, pk):
    """
    Loads the existing 'employee_list' template, 
    but pre-fills the form with the selected employee's data.
    """
    # 1. Get the employee we want to edit
    employee_to_edit = get_object_or_404(Employee, pk=pk, owner=request.user)
    
    # 2. Get the full list (so the left side table doesn't disappear!)
    employees = Employee.objects.filter(owner=request.user).order_by('name')

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
def download_labels_pdf(request):
    """
    Generates an A4 PDF with QR labels for ALL assets.
    """
    # 1. Setup the PDF Buffer
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # 210mm x 297mm basically

    # Company Name for footer
    try:
        company_name = f"Property of {request.user.userprofile.company_name}"
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

    if single_uuid:
        # Mode A: Single Asset
        assets = Asset.objects.filter(owner=request.user, uuid=single_uuid)
    elif selected_ids:
        # Mode B: Bulk Selection
        assets = Asset.objects.filter(owner=request.user, uuid__in=selected_ids).order_by('name')
    else:
        # Mode C: Print ALL (Default fallback)
        assets = Asset.objects.filter(owner=request.user).order_by('name')

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
            profile = request.user.userprofile
            comp_name = profile.company_name
            phone = profile.phone_number
            email = request.user.email
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