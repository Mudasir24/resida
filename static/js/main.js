/**
 * ============================================
 * MAIN.JS - Core Initialization
 * ============================================
 */

// Dynamic Navbar Height Adjustment
function adjustMainPadding() {
    const navbar = document.querySelector('.navbar');
    const main = document.querySelector('main');
    
    if (navbar && main) {
        const navbarHeight = navbar.offsetHeight;
        main.style.paddingTop = `${navbarHeight + 20}px`; // Add 20px extra spacing
        console.log(`📏 Navbar height: ${navbarHeight}px, Main padding set to: ${navbarHeight + 20}px`);
    }
}

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Apartment Platform Initialized');
    
    // Set initial padding based on navbar height
    adjustMainPadding();
    
    // Initialize all modules
    initScrollReveal();
    initNavbarEffects();
    initMagneticButtons();
    initCustomCursor();
    initFormEnhancements();
    
    // Log loaded modules
    console.log('✅ All modules loaded successfully');
});

// Handle page visibility
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        console.log('Page hidden');
    } else {
        console.log('Page visible');
    }
});

// Handle window resize with debouncing
let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        console.log('Window resized:', window.innerWidth, 'x', window.innerHeight);
        // Recalculate main padding on resize
        adjustMainPadding();
        // Re-initialize components that need resize handling
        initScrollReveal();
    }, 250);
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href !== '#') {
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        }
    });
});
