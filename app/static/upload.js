// State
const state = {
    selectedFiles: [],  // Array of File objects
    availableMetrics: [],  // Array of { name, display_name, description }
    selectedMetrics: new Set(),
    jobs: [],
    pollingIntervals: new Map(), // job_id -> interval
    jobFilenames: new Map(), // job_id -> original filename (for display before processing completes)
};

// DOM Elements
const elements = {
    dropZone: document.getElementById('dropZone'),
    fileInput: document.getElementById('fileInput'),
    selectedFiles: document.getElementById('selectedFiles'),
    selectedFilesList: document.getElementById('selectedFilesList'),
    metricsList: document.getElementById('metricsList'),
    submitBtn: document.getElementById('submitBtn'),
    jobsList: document.getElementById('jobsList'),
    refreshBtn: document.getElementById('refreshBtn'),
};

// Helper to get metric display name
function getMetricDisplayName(metricName) {
    const metric = state.availableMetrics.find(m => m.name === metricName);
    return metric?.display_name || metricName;
}

// API functions
async function fetchAvailableMetrics() {
    const response = await fetch('/api/metrics');
    const data = await response.json();
    return data.details;  // Returns full metric objects with display_name
}

async function fetchJobs() {
    const response = await fetch('/api/jobs');
    const data = await response.json();
    return data.jobs;
}

async function fetchJobStatus(jobId) {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) return null;
    return response.json();
}

async function submitJob(file, metrics) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('metrics', JSON.stringify(metrics));

    const response = await fetch('/api/jobs', {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
    }

    return response.json();
}

async function deleteJob(jobId) {
    const response = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
    return response.ok;
}

// UI functions
function renderMetrics() {
    elements.metricsList.innerHTML = state.availableMetrics.map(metric => {
        const checked = state.selectedMetrics.has(metric.name) ? 'checked' : '';
        return `
            <label class="metric-item">
                <input type="checkbox" class="metric-checkbox" data-metric="${metric.name}" ${checked}>
                <span class="metric-name">${metric.display_name}</span>
            </label>
        `;
    }).join('');

    // Attach listeners
    elements.metricsList.querySelectorAll('.metric-checkbox').forEach(cb => {
        cb.addEventListener('change', handleMetricToggle);
    });
}

function getJobDisplayName(job) {
    // Use font_name from server, or fall back to stored filename
    return job.font_name || state.jobFilenames.get(job.job_id) || '处理中...';
}

function renderJobs() {
    if (state.jobs.length === 0) {
        elements.jobsList.innerHTML = '<div class="empty-jobs">暂无处理任务</div>';
        return;
    }

    elements.jobsList.innerHTML = state.jobs.map(job => {
        const statusClass = `job-status-${job.status}`;
        const statusText = getStatusText(job);
        const progressBar = job.status === 'processing' ? `
            <div class="job-progress">
                <div class="job-progress-bar" style="width: ${job.progress}%"></div>
            </div>
        ` : '';

        const timeText = getTimeText(job);
        const canDelete = job.status === 'completed' || job.status === 'failed';

        const metricsDisplay = (job.requested_metrics || []).map(m => getMetricDisplayName(m)).join(', ');
        const displayName = getJobDisplayName(job);
        return `
            <div class="job-item ${statusClass}" data-job-id="${job.job_id}">
                <div class="job-header">
                    <span class="job-name">${displayName}</span>
                    ${canDelete ? `<button class="job-delete" data-job-id="${job.job_id}" title="删除">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"/>
                            <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>` : ''}
                </div>
                <div class="job-metrics">${metricsDisplay}</div>
                ${progressBar}
                <div class="job-footer">
                    <span class="job-status-text">${statusText}</span>
                    <span class="job-time">${timeText}</span>
                </div>
            </div>
        `;
    }).join('');

    // Attach delete listeners
    elements.jobsList.querySelectorAll('.job-delete').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const jobId = btn.dataset.jobId;
            if (await deleteJob(jobId)) {
                stopPollingJob(jobId);
                await loadJobs();
            }
        });
    });
}

function getStatusText(job) {
    switch (job.status) {
        case 'pending':
            return '等待中...';
        case 'processing':
            if (job.current_metric) {
                return `处理中: ${getMetricDisplayName(job.current_metric)}`;
            }
            return '处理中...';
        case 'completed':
            return '已完成';
        case 'failed':
            return `失败: ${job.error || '未知错误'}`;
        default:
            return job.status;
    }
}

function getTimeText(job) {
    const date = job.completed_at || job.started_at || job.created_at;
    if (!date) return '';
    const d = new Date(date);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function updateSubmitButton() {
    const hasFiles = state.selectedFiles.length > 0;
    const hasMetrics = state.selectedMetrics.size > 0;
    elements.submitBtn.disabled = !hasFiles || !hasMetrics;
}

function showSelectedFiles() {
    if (!elements.selectedFiles || !elements.selectedFilesList) {
        console.error('Selected files elements not found - please refresh the page');
        return;
    }

    if (state.selectedFiles.length > 0) {
        const filesHtml = state.selectedFiles.map((file, index) => `
            <div class="file-info" data-index="${index}">
                <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
                <span class="file-name">${file.name}</span>
                <button class="file-remove" data-index="${index}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
        `).join('');

        const addMoreHtml = `
            <button class="add-more-btn" id="addMoreBtn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="12" y1="5" x2="12" y2="19"/>
                    <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                添加更多文件
            </button>
        `;

        elements.selectedFilesList.innerHTML = filesHtml + addMoreHtml;

        // Attach remove listeners
        elements.selectedFilesList.querySelectorAll('.file-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const index = parseInt(btn.dataset.index);
                handleFileRemove(index);
            });
        });

        // Attach add more listener
        const addMoreBtn = elements.selectedFilesList.querySelector('#addMoreBtn');
        if (addMoreBtn) {
            addMoreBtn.addEventListener('click', () => elements.fileInput.click());
        }

        elements.selectedFiles.style.display = 'block';
        elements.dropZone.style.display = 'none';
    } else {
        elements.selectedFiles.style.display = 'none';
        elements.dropZone.style.display = 'block';
    }
    updateSubmitButton();
}

function setSubmitting(isSubmitting) {
    elements.submitBtn.disabled = isSubmitting;
    elements.submitBtn.querySelector('.submit-text').style.display = isSubmitting ? 'none' : 'inline';
    elements.submitBtn.querySelector('.submit-spinner').style.display = isSubmitting ? 'inline-block' : 'none';
}

// Update a single job element in-place (for smooth progress bar transitions)
function updateJobElement(job) {
    const jobElement = elements.jobsList.querySelector(`[data-job-id="${job.job_id}"]`);
    if (!jobElement) return false;

    // Update status class
    jobElement.className = `job-item job-status-${job.status}`;

    // Update job name
    const nameElement = jobElement.querySelector('.job-name');
    if (nameElement) {
        nameElement.textContent = getJobDisplayName(job);
    }

    // Update progress bar (in-place for smooth transition)
    let progressContainer = jobElement.querySelector('.job-progress');
    if (job.status === 'processing') {
        if (!progressContainer) {
            // Create progress bar if it doesn't exist
            progressContainer = document.createElement('div');
            progressContainer.className = 'job-progress';
            progressContainer.innerHTML = '<div class="job-progress-bar" style="width: 0%"></div>';
            const metricsElement = jobElement.querySelector('.job-metrics');
            metricsElement.insertAdjacentElement('afterend', progressContainer);
        }
        const progressBar = progressContainer.querySelector('.job-progress-bar');
        if (progressBar) {
            progressBar.style.width = `${job.progress}%`;
        }
    } else if (progressContainer) {
        progressContainer.remove();
    }

    // Update status text
    const statusText = jobElement.querySelector('.job-status-text');
    if (statusText) {
        statusText.textContent = getStatusText(job);
    }

    // Update time
    const timeElement = jobElement.querySelector('.job-time');
    if (timeElement) {
        timeElement.textContent = getTimeText(job);
    }

    // Update delete button visibility
    const canDelete = job.status === 'completed' || job.status === 'failed';
    const headerElement = jobElement.querySelector('.job-header');
    const existingDelete = headerElement.querySelector('.job-delete');

    if (canDelete && !existingDelete) {
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'job-delete';
        deleteBtn.dataset.jobId = job.job_id;
        deleteBtn.title = '删除';
        deleteBtn.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        `;
        deleteBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (await deleteJob(job.job_id)) {
                stopPollingJob(job.job_id);
                await loadJobs();
            }
        });
        headerElement.appendChild(deleteBtn);
    }

    return true;
}

// Polling
function startPollingJob(jobId) {
    if (state.pollingIntervals.has(jobId)) return;

    const interval = setInterval(async () => {
        const job = await fetchJobStatus(jobId);
        if (!job) {
            stopPollingJob(jobId);
            return;
        }

        // Update job in state
        const index = state.jobs.findIndex(j => j.job_id === jobId);
        if (index !== -1) {
            state.jobs[index] = job;
            // Try to update in-place for smooth transitions
            if (!updateJobElement(job)) {
                renderJobs();
            }
        }

        // Stop polling if job is done
        if (job.status === 'completed' || job.status === 'failed') {
            stopPollingJob(jobId);
        }
    }, 1000);

    state.pollingIntervals.set(jobId, interval);
}

function stopPollingJob(jobId) {
    const interval = state.pollingIntervals.get(jobId);
    if (interval) {
        clearInterval(interval);
        state.pollingIntervals.delete(jobId);
    }
}

function stopAllPolling() {
    state.pollingIntervals.forEach((interval, jobId) => {
        clearInterval(interval);
    });
    state.pollingIntervals.clear();
}

// Event handlers
function handleMetricToggle(e) {
    const metric = e.target.dataset.metric;
    if (e.target.checked) {
        state.selectedMetrics.add(metric);
    } else {
        state.selectedMetrics.delete(metric);
    }
    updateSubmitButton();
}

function handleFileDrop(e) {
    e.preventDefault();
    elements.dropZone.classList.remove('drag-over');

    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
        state.selectedFiles = [...state.selectedFiles, ...Array.from(files)];
        showSelectedFiles();
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files && files.length > 0) {
        state.selectedFiles = [...state.selectedFiles, ...Array.from(files)];
        showSelectedFiles();
    }
    // Reset input so the same file can be selected again
    elements.fileInput.value = '';
}

function handleFileRemove(index) {
    state.selectedFiles.splice(index, 1);
    if (state.selectedFiles.length === 0) {
        elements.fileInput.value = '';
    }
    showSelectedFiles();
}

async function handleSubmit() {
    if (state.selectedFiles.length === 0 || state.selectedMetrics.size === 0) return;

    setSubmitting(true);
    const filesToUpload = [...state.selectedFiles];
    const metrics = Array.from(state.selectedMetrics);

    // Reset form immediately
    state.selectedFiles = [];
    elements.fileInput.value = '';
    showSelectedFiles();

    try {
        // Submit all files in parallel
        const results = await Promise.all(
            filesToUpload.map(async (file) => {
                try {
                    const result = await submitJob(file, metrics);
                    // Store the filename for this job (for display before processing completes)
                    state.jobFilenames.set(result.job_id, file.name);
                    return { success: true, job_id: result.job_id };
                } catch (error) {
                    return { success: false, filename: file.name, error: error.message };
                }
            })
        );

        // Report any failures
        const failures = results.filter(r => !r.success);
        if (failures.length > 0) {
            const failedNames = failures.map(f => f.filename).join(', ');
            alert(`部分文件上传失败: ${failedNames}`);
        }

        // Reload jobs and start polling for successful uploads
        await loadJobs();
        results.filter(r => r.success).forEach(r => startPollingJob(r.job_id));
    } catch (error) {
        console.error('Submit failed:', error);
        alert(`上传失败: ${error.message}`);
    } finally {
        setSubmitting(false);
    }
}

async function loadJobs() {
    state.jobs = await fetchJobs();
    renderJobs();

    // Start polling for active jobs
    state.jobs.forEach(job => {
        if (job.status === 'pending' || job.status === 'processing') {
            startPollingJob(job.job_id);
        }
    });
}

// Initialize
async function init() {
    // Load available metrics
    try {
        state.availableMetrics = await fetchAvailableMetrics();
        // Select all by default (use metric names, not full objects)
        state.selectedMetrics = new Set(state.availableMetrics.map(m => m.name));
        renderMetrics();
    } catch (error) {
        console.error('Failed to load metrics:', error);
    }

    // Load existing jobs
    await loadJobs();

    // Drop zone events
    elements.dropZone.addEventListener('click', () => elements.fileInput.click());
    elements.dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.dropZone.classList.add('drag-over');
    });
    elements.dropZone.addEventListener('dragleave', () => {
        elements.dropZone.classList.remove('drag-over');
    });
    elements.dropZone.addEventListener('drop', handleFileDrop);

    // File input
    elements.fileInput.addEventListener('change', handleFileSelect);

    // Submit
    elements.submitBtn.addEventListener('click', handleSubmit);

    // Refresh
    elements.refreshBtn.addEventListener('click', loadJobs);
}

init();
