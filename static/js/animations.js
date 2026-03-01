/**
 * ============================================
 * ANIMATIONS.JS - Scroll Reveal & Navbar
 * ============================================
 */

/**
 * Initialize Scroll Reveal using Intersection Observer API
 */
function initScrollReveal() {
    // Configuration for Intersection Observer
    const observerOptions = {
        threshold: 0.15, // Trigger when 15% of element is visible
        rootMargin: '0px 0px -50px 0px' // Trigger slightly before element enters viewport
    };

    // Create the observer
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // Add 'active' class when element enters viewport
                entry.target.classList.add('active');
                
                // Optional: Stop observing after animation (for performance)
                // observer.unobserve(entry.target);
            } else {
                // Optional: Remove class when scrolling back up for repeat animation
                // entry.target.classList.remove('active');
            }
        });
    }, observerOptions);

    // Observe all elements with reveal classes
    const revealElements = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale');
    revealElements.forEach(element => observer.observe(element));

    console.log(`📜 Scroll Reveal: Watching ${revealElements.length} elements`);
}

/**
 * Initialize Navbar Scroll Effects
 */
function initNavbarEffects() {
    const navbar = document.querySelector('.navbar');
    if (!navbar) return;

    let lastScrollTop = 0;
    const scrollThreshold = 50; // Pixels to scroll before adding 'scrolled' class

    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

        // Add 'scrolled' class when scrolling down past threshold
        if (scrollTop > scrollThreshold) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }

        // Optional: Hide navbar on scroll down, show on scroll up
        // if (scrollTop > lastScrollTop && scrollTop > 200) {
        //     navbar.style.transform = 'translateY(-100%)';
        // } else {
        //     navbar.style.transform = 'translateY(0)';
        // }

        lastScrollTop = scrollTop;
    });

    console.log('🎯 Navbar effects initialized');
}

/**
 * Animate elements on page load
 */
function animateOnLoad() {
    const hero = document.querySelector('.hero');
    if (hero) {
        hero.style.opacity = '0';
        setTimeout(() => {
            hero.style.transition = 'opacity 1s ease';
            hero.style.opacity = '1';
        }, 100);
    }
}

// Run on load
window.addEventListener('load', animateOnLoad);

/**
 * Parallax effect for hero section (optional)
 */
function initParallax() {
    const hero = document.querySelector('.hero');
    if (!hero) return;

    window.addEventListener('scroll', () => {
        const scrolled = window.pageYOffset;
        const parallaxSpeed = 0.5;
        
        if (scrolled < window.innerHeight) {
            hero.style.transform = `translateY(${scrolled * parallaxSpeed}px)`;
        }
    });

    console.log('🌊 Parallax effect initialized');
}

// Uncomment to enable parallax
// initParallax();
