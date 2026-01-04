document.addEventListener('DOMContentLoaded', function() {
    const statusField = document.getElementById('id_status');
    const assignedField = document.getElementById('id_assigned_to');
    
    // SAFETY CHECK
    if (!statusField || !assignedField) {
        return;
    }

    // 1. MEMORY
    let lastKnownName = assignedField.value;

    // 2. LISTENER
    assignedField.addEventListener('input', function() {
        lastKnownName = assignedField.value;
    });

    // 3. LOGIC
    function toggleAssignedField() {
        const selectedStatus = statusField.value;
        
        if (selectedStatus === 'ASSIGNED') {
            assignedField.disabled = false;
            assignedField.value = lastKnownName; // Restore
            assignedField.placeholder = "Employee Name (Required)";
        } else {
            assignedField.disabled = true;
            assignedField.value = ""; // Clear visual
            assignedField.placeholder = "Not applicable";
        }
    }

    // Init
    if (statusField.value !== 'ASSIGNED') {
        assignedField.disabled = true;
        assignedField.value = "";
    }
    
    statusField.addEventListener('change', toggleAssignedField);
});