// SQLite Cult - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide messages after 5 seconds
    document.querySelectorAll('.message').forEach(function(msg) {
        setTimeout(function() {
            msg.style.opacity = '0';
            msg.style.transform = 'translateY(-10px)';
            setTimeout(function() {
                msg.remove();
            }, 300);
        }, 5000);
    });

    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.dropdown')) {
            document.querySelectorAll('.dropdown.active').forEach(function(dropdown) {
                dropdown.classList.remove('active');
            });
        }
    });

    // Handle keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Escape closes modals
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(function(modal) {
                modal.classList.remove('active');
            });
            document.querySelectorAll('.confirm-overlay').forEach(function(confirm) {
                confirm.style.display = 'none';
            });
        }
        
        // Ctrl/Cmd + Enter executes query
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            const queryInput = document.getElementById('query-input');
            if (queryInput && document.activeElement === queryInput) {
                e.preventDefault();
                if (typeof executeQuery === 'function') {
                    executeQuery();
                }
            }
        }
    });

    // Textarea auto-resize
    document.querySelectorAll('textarea.form-input').forEach(function(textarea) {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.max(this.scrollHeight, 80) + 'px';
        });
    });

    // Form validation styling
    document.querySelectorAll('form').forEach(function(form) {
        form.addEventListener('submit', function() {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                const originalText = submitBtn.innerHTML;
                submitBtn.innerHTML = '<div class="spinner" style="width: 16px; height: 16px;"></div> Processing...';
                setTimeout(function() {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                }, 10000);
            }
        });
    });
});

// Modal functions
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        const firstInput = modal.querySelector('input, textarea, select');
        if (firstInput) {
            setTimeout(function() {
                firstInput.focus();
            }, 100);
        }
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showToast('Copied to clipboard');
    }).catch(function(err) {
        console.error('Failed to copy:', err);
    });
}

// Simple toast notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `message message-${type}`;
    toast.style.cssText = 'position: fixed; bottom: 1rem; right: 1rem; z-index: 1000; max-width: 300px;';
    toast.innerHTML = `<span>${message}</span>`;
    document.body.appendChild(toast);
    
    setTimeout(function() {
        toast.style.opacity = '0';
        setTimeout(function() {
            toast.remove();
        }, 300);
    }, 3000);
}

// Confirmation dialog
function confirmAction(message, onConfirm) {
    if (confirm(message)) {
        onConfirm();
    }
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = function() {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Table cell value editing (inline)
function makeEditable(cell, saveCallback) {
    const originalValue = cell.textContent;
    const input = document.createElement('input');
    input.type = 'text';
    input.value = originalValue === 'NULL' ? '' : originalValue;
    input.className = 'form-input';
    input.style.cssText = 'padding: 0.25rem; font-size: inherit;';
    
    cell.innerHTML = '';
    cell.appendChild(input);
    input.focus();
    input.select();
    
    function save() {
        const newValue = input.value;
        cell.textContent = newValue || 'NULL';
        if (newValue !== originalValue) {
            saveCallback(newValue);
        }
    }
    
    function cancel() {
        cell.textContent = originalValue;
    }
    
    input.addEventListener('blur', save);
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            save();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancel();
        }
    });
}

// SQL syntax helper
const sqlKeywords = [
    'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN',
    'ORDER BY', 'GROUP BY', 'HAVING', 'LIMIT', 'OFFSET', 'JOIN', 'LEFT JOIN',
    'RIGHT JOIN', 'INNER JOIN', 'OUTER JOIN', 'ON', 'AS', 'DISTINCT', 'COUNT',
    'SUM', 'AVG', 'MIN', 'MAX', 'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET',
    'DELETE', 'CREATE', 'TABLE', 'INDEX', 'DROP', 'ALTER', 'ADD', 'COLUMN',
    'PRIMARY KEY', 'FOREIGN KEY', 'REFERENCES', 'UNIQUE', 'NOT NULL', 'DEFAULT',
    'AUTOINCREMENT', 'INTEGER', 'TEXT', 'REAL', 'BLOB', 'NUMERIC', 'BOOLEAN',
    'DATE', 'DATETIME', 'TIMESTAMP', 'NULL', 'TRUE', 'FALSE', 'ASC', 'DESC'
];

// Export functions for use in templates
window.openModal = openModal;
window.closeModal = closeModal;
window.copyToClipboard = copyToClipboard;
window.showToast = showToast;
window.confirmAction = confirmAction;
