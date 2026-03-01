/* ============================================
   THEME TOGGLE - Light/Dark Mode
   ============================================ */

// Initialize theme from localStorage or default to light
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
}

// Toggle theme
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    // Add subtle animation
    document.body.style.transition = 'background-color 0.3s ease, color 0.3s ease';
    setTimeout(() => {
        document.body.style.transition = '';
    }, 300);
}

// Create and inject theme toggle button
function createThemeToggle() {
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'theme-toggle';
    toggleBtn.setAttribute('aria-label', 'Toggle theme');
    toggleBtn.innerHTML = `
        <div class="theme-toggle-icon">
            <svg class="sun-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="5" fill="currentColor"/>
                <path d="M12 1v6m0 6v6m11-7h-6m-6 0H1m18.364-6.364l-4.243 4.243m-6.243 0L4.636 4.636m14.728 14.728l-4.243-4.243m-6.243 0L4.636 19.364" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <svg class="moon-icon" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
        </div>
    `;
    
    toggleBtn.addEventListener('click', toggleTheme);
    document.body.appendChild(toggleBtn);
}

// Initialize on DOM load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        initTheme();
        createThemeToggle();
    });
} else {
    initTheme();
    createThemeToggle();
}
