/**
 * Micraft Growth Engine - Calling System JS
 */

async function updateCallStatus(leadId, event) {
  event.preventDefault();
  const form = event.target;
  const formData = new FormData(form);
  const data = Object.fromEntries(formData.entries());
  
  // Format the date if it's empty
  if (!data.follow_up_date) {
    delete data.follow_up_date;
  }
  
  const submitBtn = form.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.innerText = "Saving...";

  try {
    const response = await fetch(`/api/calling/leads/${leadId}/update-call`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data)
    });

    if (response.ok) {
      alert("Call logged successfully!");
      // Optionally redirect back to workboard or refresh
      window.location.reload();
    } else {
      const err = await response.json();
      alert("Error: " + (err.detail || "Failed to update"));
      submitBtn.disabled = false;
      submitBtn.innerText = "Save Call Log";
    }
  } catch (error) {
    console.error("Error:", error);
    alert("Network error.");
    submitBtn.disabled = false;
    submitBtn.innerText = "Save Call Log";
  }
}

function handleStatusChange() {
  const statusSelect = document.getElementById('call_status');
  const followUpGroup = document.getElementById('follow_up_group');
  
  if (statusSelect.value === 'follow_up') {
    followUpGroup.style.display = 'block';
  } else {
    followUpGroup.style.display = 'none';
  }
}

async function handleCSVUpload(event) {
  event.preventDefault();
  const form = event.target;
  const fileInput = document.getElementById('csv_file');
  
  if (!fileInput.files.length) {
    alert("Please select a file");
    return;
  }
  
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  const submitBtn = form.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.innerText = "Uploading...";

  try {
    const response = await fetch('/api/calling/import-csv', {
      method: 'POST',
      body: formData
    });

    const result = await response.json();
    if (response.ok) {
        document.getElementById('upload-result').innerHTML = `
            <div style="color: var(--status-interested); font-weight: bold; margin-top: 15px;">
                ${result.message}
            </div>
        `;
        form.reset();
    } else {
        alert("Error: " + (result.detail || "Failed to upload"));
    }
  } catch (error) {
    console.error("Error:", error);
    alert("Network error during upload.");
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerText = "Upload CSV";
  }
}
