(function () {
    var header = document.getElementById("site-header");

    function updateHeaderState() {
        if (window.scrollY > 24) {
            header.classList.add("is-scrolled");
        } else {
            header.classList.remove("is-scrolled");
        }
    }

    if (header) {
        updateHeaderState();
        window.addEventListener("scroll", updateHeaderState, { passive: true });
    }

    var navToggle = document.getElementById("nav-toggle");
    var mobileNav = document.getElementById("mobile-nav");

    if (navToggle && mobileNav) {
        navToggle.addEventListener("click", function () {
            var isOpen = navToggle.getAttribute("aria-expanded") === "true";
            navToggle.setAttribute("aria-expanded", String(!isOpen));
            mobileNav.hidden = isOpen;
        });

        mobileNav.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", function () {
                navToggle.setAttribute("aria-expanded", "false");
                mobileNav.hidden = true;
            });
        });
    }

    if (!("IntersectionObserver" in window)) {
        return;
    }

    document.body.classList.add("js-ready");

    var cards = document.querySelectorAll(".product-card");
    var observer = new IntersectionObserver(
        function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.15 }
    );

    cards.forEach(function (card) {
        observer.observe(card);
    });
})();
