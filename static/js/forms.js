/**
 * ============================================
 * FORMS.JS - Form Enhancements
 * ============================================
 */

/**
 * Initialize all form enhancements
 */
function initFormEnhancements() {
    initSlugPreview();
    initFormValidation();
    initInputAnimations();
    console.log('📝 Form enhancements initialized');
}

/**
 * Real-time slug preview for apartment registration
 */
function initSlugPreview() {
    const slugInput = document.getElementById('slug');
    const slugPreview = document.getElementById('slug-preview');
    
    if (slugInput && slugPreview) {
        slugInput.addEventListener('input', (e) => {
            const value = e.target.value || 'your-slug';
            slugPreview.textContent = value;
            
            // Validate slug format (lowercase, numbers, hyphens only)
            const validSlug = /^[a-z0-9-]+$/.test(value);
            if (!validSlug && value !== '') {
                slugInput.style.borderColor = '#ef4444';
            } else {
                slugInput.style.borderColor = 'rgba(255, 255, 255, 0.1)';
            }
        });
    }
}

/**
 * Add real-time validation to forms
 */
function initFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        const inputs = form.querySelectorAll('input[required], textarea[required]');
        
        inputs.forEach(input => {
            // Validate on blur
            input.addEventListener('blur', () => {
                validateInput(input);
            });
            
            // Clear error on focus
            input.addEventListener('focus', () => {
                clearInputError(input);
            });
        });
        
        // Validate on submit
        form.addEventListener('submit', (e) => {
            let isValid = true;
            
            inputs.forEach(input => {
                if (!validateInput(input)) {
                    isValid = false;
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                showFormError(form, 'Please fill in all required fields correctly.');
            }
        });
    });
}

/**
 * Validate individual input
 */
function validateInput(input) {
    const value = input.value.trim();
    const type = input.type;
    
    // Check if empty
    if (input.hasAttribute('required') && value === '') {
        setInputError(input, 'This field is required');
        return false;
    }
    
    // Email validation
    if (type === 'email' && value !== '') {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            setInputError(input, 'Please enter a valid email address');
            return false;
        }
    }
    
    // Password validation (if has pattern or minlength)
    if (type === 'password' && input.hasAttribute('minlength')) {
        const minLength = parseInt(input.getAttribute('minlength'));
        if (value.length < minLength) {
            setInputError(input, `Password must be at least ${minLength} characters`);
            return false;
        }
    }
    
    // Pattern validation
    if (input.hasAttribute('pattern') && value !== '') {
        const pattern = new RegExp(input.getAttribute('pattern'));
        if (!pattern.test(value)) {
            setInputError(input, 'Please match the required format');
            return false;
        }
    }
    
    clearInputError(input);
    return true;
}

/**
 * Set input error state
 */
function setInputError(input, message) {
    input.style.borderColor = '#ef4444';
    
    // Remove existing error message
    const existingError = input.parentElement.querySelector('.error-message');
    if (existingError) {
        existingError.remove();
    }
    
    // Add error message
    const errorDiv = document.createElement('small');
    errorDiv.className = 'error-message';
    errorDiv.style.color = '#ef4444';
    errorDiv.style.display = 'block';
    errorDiv.style.marginTop = '0.25rem';
    errorDiv.textContent = message;
    
    input.parentElement.appendChild(errorDiv);
}

/**
 * Clear input error state
 */
function clearInputError(input) {
    input.style.borderColor = 'rgba(255, 255, 255, 0.1)';
    
    const errorMessage = input.parentElement.querySelector('.error-message');
    if (errorMessage) {
        errorMessage.remove();
    }
}

/**
 * Show form-level error message
 */
function showFormError(form, message) {
    // Remove existing form error
    const existingError = form.querySelector('.form-error');
    if (existingError) {
        existingError.remove();
    }
    
    // Create error alert
    const errorDiv = document.createElement('div');
    errorDiv.className = 'alert alert-error form-error';
    errorDiv.textContent = message;
    
    // Insert at beginning of form
    form.insertBefore(errorDiv, form.firstChild);
    
    // Scroll to error
    errorDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    // Auto-remove after 5 seconds
    setTimeout(() => errorDiv.remove(), 5000);
}

/**
 * Add floating label animation to inputs
 */
function initInputAnimations() {
    const inputs = document.querySelectorAll('input, textarea, select');
    
    inputs.forEach(input => {
        // Add focus class
        input.addEventListener('focus', () => {
            input.parentElement.classList.add('input-focused');
        });
        
        // Remove focus class
        input.addEventListener('blur', () => {
            input.parentElement.classList.remove('input-focused');
        });
        
        // Check if input has value on load
        if (input.value !== '') {
            input.parentElement.classList.add('input-has-value');
        }
        
        // Monitor value changes
        input.addEventListener('input', () => {
            if (input.value !== '') {
                input.parentElement.classList.add('input-has-value');
            } else {
                input.parentElement.classList.remove('input-has-value');
            }
        });
    });
}

/**
 * Auto-save form data to localStorage (optional)
 */
function initAutoSave(formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    
    const inputs = form.querySelectorAll('input:not([type="password"]), textarea, select');
    const storageKey = `form_${formId}_autosave`;
    
    // Load saved data
    const savedData = localStorage.getItem(storageKey);
    if (savedData) {
        const data = JSON.parse(savedData);
        inputs.forEach(input => {
            if (data[input.name]) {
                input.value = data[input.name];
            }
        });
    }
    
    // Save on input
    inputs.forEach(input => {
        input.addEventListener('input', () => {
            const data = {};
            inputs.forEach(i => {
                data[i.name] = i.value;
            });
            localStorage.setItem(storageKey, JSON.stringify(data));
        });
    });
    
    // Clear on submit
    form.addEventListener('submit', () => {
        localStorage.removeItem(storageKey);
    });
    
    console.log(`💾 Auto-save enabled for form: ${formId}`);
}

// Uncomment to enable auto-save for specific forms
// initAutoSave('registration-form');
