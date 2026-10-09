(function () {
    var CURRENCY_SUFFIX = " ֏"; // " ֏"

    function getCookie(name) {
        var prefix = name + "=";
        var cookies = document.cookie ? document.cookie.split("; ") : [];
        for (var i = 0; i < cookies.length; i++) {
            if (cookies[i].indexOf(prefix) === 0) {
                return decodeURIComponent(cookies[i].slice(prefix.length));
            }
        }
        return null;
    }

    function formatAmount(value) {
        var number = Number(value);
        if (isNaN(number)) {
            return value + CURRENCY_SUFFIX;
        }
        return formatNumber(number) + CURRENCY_SUFFIX;
    }

    function formatNumber(value) {
        var number = Number(value);
        if (isNaN(number)) {
            return value;
        }
        return number.toLocaleString("en-US").replace(/,/g, "'");
    }

    function readInitialState() {
        var el = document.getElementById("basket-data");
        if (!el) {
            return { items: [], count: 0, total: "0" };
        }
        try {
            return JSON.parse(el.textContent);
        } catch (err) {
            return { items: [], count: 0, total: "0" };
        }
    }

    function postJson(url, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(body || {}),
        }).then(function (response) {
            return response.json();
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        var state = readInitialState();

        var orderButton = document.getElementById("order-button");
        var orderButtonCount = document.getElementById("order-button-count");
        var modal = document.getElementById("order-modal");
        var modalItems = document.getElementById("order-modal-items");
        var modalEmpty = document.getElementById("order-modal-empty");
        var modalTotal = document.getElementById("order-modal-total");
        var submitButton = document.getElementById("order-form-submit");
        var addressInput = document.getElementById("id_address");
        var locationButton = document.getElementById("address-location-button");
        var locationStatus = document.getElementById("address-location-status");

        function setLocationStatus(message, isError) {
            if (!locationStatus) {
                return;
            }
            locationStatus.textContent = message;
            locationStatus.hidden = false;
            locationStatus.classList.toggle("is-error", Boolean(isError));
        }

        function finishLocationLookup() {
            locationButton.disabled = false;
            locationButton.removeAttribute("aria-busy");
        }

        function geolocationErrorMessage(error) {
            if (error.code === error.PERMISSION_DENIED) {
                return "Տեղադրությունը գտնելու համար թույլատրեք հասանելիությունը։";
            }
            if (error.code === error.POSITION_UNAVAILABLE) {
                return "Չհաջողվեց որոշել Ձեր գտնվելու վայրը։";
            }
            if (error.code === error.TIMEOUT) {
                return "Տեղադրության որոշումը շատ երկար տևեց։ Փորձեք կրկին։";
            }
            return "Չհաջողվեց գտնել Ձեր գտնվելու վայրը։";
        }

        function resolveAddress(position) {
            var controller = new AbortController();
            var timeoutId = window.setTimeout(function () {
                controller.abort();
            }, 10000);
            var latitude = encodeURIComponent(position.coords.latitude);
            var longitude = encodeURIComponent(position.coords.longitude);
            var url =
                "https://nominatim.openstreetmap.org/reverse?format=jsonv2" +
                "&lat=" + latitude +
                "&lon=" + longitude +
                "&zoom=18&addressdetails=1&accept-language=hy,en";

            fetch(url, {
                headers: { Accept: "application/json" },
                signal: controller.signal,
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("Reverse geocoding failed");
                    }
                    return response.json();
                })
                .then(function (result) {
                    if (!result || typeof result.display_name !== "string") {
                        throw new Error("Invalid reverse geocoding response");
                    }
                    addressInput.value = result.display_name;
                    addressInput.dispatchEvent(new Event("input", { bubbles: true }));
                    setLocationStatus("Հասցեն գտնված է։", false);
                })
                .catch(function () {
                    setLocationStatus(
                        "Տեղադրությունը գտնվեց, բայց հասցեն որոշել չհաջողվեց։ Մուտքագրեք այն ձեռքով։",
                        true
                    );
                })
                .finally(function () {
                    window.clearTimeout(timeoutId);
                    finishLocationLookup();
                });
        }

        function findItem(productId) {
            for (var i = 0; i < state.items.length; i++) {
                if (state.items[i].product_id === productId) {
                    return state.items[i];
                }
            }
            return null;
        }

        function renderOrderButton() {
            if (state.count > 0) {
                orderButtonCount.hidden = false;
                orderButtonCount.textContent = "(" + formatNumber(state.count) + ")";
            } else {
                orderButtonCount.hidden = true;
            }
        }

        function renderProductCards() {
            document.querySelectorAll(".product-card__order").forEach(function (el) {
                var productId = el.dataset.productId;
                var addButton = el.querySelector('[data-role="add"]');
                var stepper = el.querySelector('[data-role="stepper"]');
                var quantityLabel = stepper.querySelector('[data-role="quantity"]');
                var item = findItem(productId);

                if (item) {
                    addButton.hidden = true;
                    stepper.hidden = false;
                    quantityLabel.textContent = formatNumber(item.quantity);
                } else {
                    addButton.hidden = false;
                    stepper.hidden = true;
                }
            });
        }

        function renderModal() {
            if (state.items.length === 0) {
                modalItems.innerHTML = "";
                modalEmpty.hidden = false;
            } else {
                modalEmpty.hidden = true;
                modalItems.innerHTML = state.items
                    .map(function (item) {
                        return (
                            '<div class="order-modal__item" data-product-id="' +
                            item.product_id +
                            '">' +
                            '<div class="order-modal__item-info">' +
                            '<p class="order-modal__item-name">' +
                            escapeHtml(item.name) +
                            "</p>" +
                            '<p class="order-modal__item-price">' +
                            formatAmount(item.line_total) +
                            "</p>" +
                            "</div>" +
                            '<div class="order-modal__item-controls">' +
                            '<button type="button" class="stepper__btn" data-action="decrease" aria-label="Նվազեցնել քանակը">−</button>' +
                            '<span class="stepper__value">' +
                            formatNumber(item.quantity) +
                            "</span>" +
                            '<button type="button" class="stepper__btn" data-action="increase" aria-label="Ավելացնել քանակը">+</button>' +
                            '<button type="button" class="order-modal__remove" data-action="remove" aria-label="Հեռացնել">×</button>' +
                            "</div>" +
                            "</div>"
                        );
                    })
                    .join("");
            }
            modalTotal.textContent = formatAmount(state.total);
            if (submitButton) {
                submitButton.disabled = state.items.length === 0;
            }
        }

        function escapeHtml(value) {
            var div = document.createElement("div");
            div.textContent = value;
            return div.innerHTML;
        }

        function render() {
            renderOrderButton();
            renderProductCards();
            renderModal();
        }

        function applyState(newState) {
            state = newState;
            render();
        }

        function openModal() {
            modal.hidden = false;
        }

        function closeModal() {
            modal.hidden = true;
        }

        if (orderButton) {
            orderButton.addEventListener("click", openModal);
        }

        if (locationButton && addressInput) {
            locationButton.addEventListener("click", function () {
                if (!("geolocation" in navigator)) {
                    setLocationStatus(
                        "Ձեր դիտարկիչը չի աջակցում տեղադրության որոշմանը։",
                        true
                    );
                    return;
                }

                locationButton.disabled = true;
                locationButton.setAttribute("aria-busy", "true");
                setLocationStatus("Որոշվում է Ձեր գտնվելու վայրը…", false);
                navigator.geolocation.getCurrentPosition(
                    resolveAddress,
                    function (error) {
                        setLocationStatus(geolocationErrorMessage(error), true);
                        finishLocationLookup();
                    },
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
                );
            });
        }

        if (modal) {
            modal.querySelectorAll('[data-role="close"]').forEach(function (el) {
                el.addEventListener("click", closeModal);
            });
            document.addEventListener("keydown", function (event) {
                if (event.key === "Escape" && !modal.hidden) {
                    closeModal();
                }
            });
        }

        document.querySelectorAll(".order-modal").forEach(function (dialogEl) {
            if (dialogEl === modal) {
                return;
            }
            dialogEl.querySelectorAll('[data-role="close"]').forEach(function (el) {
                el.addEventListener("click", function () {
                    dialogEl.hidden = true;
                });
            });
            document.addEventListener("keydown", function (event) {
                if (event.key === "Escape" && !dialogEl.hidden) {
                    dialogEl.hidden = true;
                }
            });
        });

        document.querySelectorAll(".product-card__order").forEach(function (el) {
            var productId = el.dataset.productId;
            var addButton = el.querySelector('[data-role="add"]');
            var stepper = el.querySelector('[data-role="stepper"]');

            addButton.addEventListener("click", function () {
                postJson("/api/basket/items/", {
                    product_id: productId,
                    quantity: 1,
                }).then(applyState);
            });

            stepper.querySelectorAll("[data-action]").forEach(function (button) {
                button.addEventListener("click", function () {
                    var item = findItem(productId);
                    var currentQuantity = item ? item.quantity : 0;
                    var delta = button.dataset.action === "increase" ? 1 : -1;
                    postJson(
                        "/api/basket/items/" + productId + "/update/",
                        { quantity: currentQuantity + delta }
                    ).then(applyState);
                });
            });
        });

        if (modalItems) {
            modalItems.addEventListener("click", function (event) {
                var button = event.target.closest("[data-action]");
                if (!button) {
                    return;
                }
                var row = event.target.closest(".order-modal__item");
                var productId = row.dataset.productId;
                var action = button.dataset.action;

                if (action === "remove") {
                    postJson("/api/basket/items/" + productId + "/remove/").then(
                        applyState
                    );
                    return;
                }

                var item = findItem(productId);
                var currentQuantity = item ? item.quantity : 0;
                var delta = action === "increase" ? 1 : -1;
                postJson("/api/basket/items/" + productId + "/update/", {
                    quantity: currentQuantity + delta,
                }).then(applyState);
            });
        }

        render();
    });
})();
