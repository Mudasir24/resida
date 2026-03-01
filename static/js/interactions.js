/**
 * ============================================
 * INTERACTIONS.JS - Magnetic Buttons & Cursor
 * ============================================
 */

/**
 * Initialize Magnetic Button Effect
 * Buttons follow the mouse when hovering
 */
function initMagneticButtons() {
    const magneticButtons = document.querySelectorAll('.btn-primary, .btn-secondary');
    
    magneticButtons.forEach(button => {
        // Add magnetic class
        button.classList.add('magnetic');

        button.addEventListener('mousemove', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left - rect.width / 2;
            const y = e.clientY - rect.top - rect.height / 2;
            
            // Magnetic strength (adjust for more/less effect)
            const strength = 0.3;
            
            this.style.transform = `translate(${x * strength}px, ${y * strength}px)`;
        });

        button.addEventListener('mouseleave', function() {
            this.style.transform = 'translate(0, 0)';
        });
    });

    console.log(`🧲 Magnetic effect: ${magneticButtons.length} buttons`);
}

/**
 * Initialize Custom Cursor Effect
 * Creates a custom cursor that follows the mouse
 */
function initCustomCursor() {
    // Custom cursor disabled by user preference
    console.log('🖱️ Custom cursor disabled');
    return;
    
    // Only enable on devices with mouse (not touch)
    if ('ontouchstart' in window || navigator.maxTouchPoints > 0) {
        console.log('👆 Touch device detected, skipping custom cursor');
        return;
    }

    // Create cursor elements
    const cursorDot = document.createElement('div');
    const cursorOutline = document.createElement('div');
    
    cursorDot.className = 'cursor-dot';
    cursorOutline.className = 'cursor-outline';
    
    document.body.appendChild(cursorDot);
    document.body.appendChild(cursorOutline);
    
    // Show cursor elements
    cursorDot.style.display = 'block';
    cursorOutline.style.display = 'block';

    // Track mouse position
    let mouseX = 0;
    let mouseY = 0;
    let outlineX = 0;
    let outlineY = 0;

    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;
        
        // Update dot position (instant)
        cursorDot.style.left = mouseX + 'px';
        cursorDot.style.top = mouseY + 'px';
    });

    // Smooth outline animation
    function animateOutline() {
        // Easing for smooth follow effect
        outlineX += (mouseX - outlineX) * 0.15;
        outlineY += (mouseY - outlineY) * 0.15;
        
        cursorOutline.style.left = outlineX + 'px';
        cursorOutline.style.top = outlineY + 'px';
        
        requestAnimationFrame(animateOutline);
    }
    animateOutline();

    // Add hover effects on interactive elements
    const interactiveElements = document.querySelectorAll('a, button, .btn, input[type="submit"]');
    
    interactiveElements.forEach(el => {
        el.addEventListener('mouseenter', () => {
            cursorDot.style.transform = 'scale(2)';
            cursorOutline.style.width = '48px';
            cursorOutline.style.height = '48px';
            document.body.classList.add('cursor-hover');
        });
        
        el.addEventListener('mouseleave', () => {
            cursorDot.style.transform = 'scale(1)';
            cursorOutline.style.width = '32px';
            cursorOutline.style.height = '32px';
            document.body.classList.remove('cursor-hover');
        });
    });

    // Hide default cursor
    document.body.style.cursor = 'none';
    interactiveElements.forEach(el => {
        el.style.cursor = 'none';
    });

    console.log('🖱️ Custom cursor initialized');
}

/**
 * Add ripple effect on button clicks
 */
function initRippleEffect() {
    const buttons = document.querySelectorAll('.btn');
    
    buttons.forEach(button => {
        button.addEventListener('click', function(e) {
            // Create ripple element
            const ripple = document.createElement('span');
            ripple.style.position = 'absolute';
            ripple.style.borderRadius = '50%';
            ripple.style.background = 'rgba(255, 255, 255, 0.5)';
            ripple.style.width = '20px';
            ripple.style.height = '20px';
            ripple.style.animation = 'ripple 0.6s ease-out';
            ripple.style.pointerEvents = 'none';
            
            // Position ripple
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            
            this.appendChild(ripple);
            
            // Remove after animation
            setTimeout(() => ripple.remove(), 600);
        });
    });

    // Add ripple animation to CSS if not exists
    if (!document.querySelector('#ripple-style')) {
        const style = document.createElement('style');
        style.id = 'ripple-style';
        style.textContent = `
            @keyframes ripple {
                to {
                    transform: scale(4);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }

    console.log(`💧 Ripple effect: ${buttons.length} buttons`);
}

// Initialize ripple effect
initRippleEffect();

/**
 * Add tilt effect to cards on mouse move
 */
function initCardTilt() {
    const cards = document.querySelectorAll('.feature-card, .apartment-card, .dashboard-card');
    
    cards.forEach(card => {
        card.addEventListener('mousemove', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            
            const rotateX = (y - centerY) / 20;
            const rotateY = (centerX - x) / 20;
            
            this.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.02)`;
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
        });
    });

    console.log(`🎴 Card tilt: ${cards.length} cards`);
}

// Initialize card tilt
initCardTilt();
