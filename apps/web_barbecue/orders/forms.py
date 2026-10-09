from django import forms

# The storefront currently only fulfills orders within Vanadzor. Matching
# on either the current name or its Soviet-era name (Kirovakan) - still
# how some long-time residents refer to the same city - avoids rejecting
# a genuine Vanadzor address over which name the customer happened to
# write, while still rejecting addresses in a different city entirely.
DELIVERY_CITY_ALIASES = ("վանաձոր", "vanadzor", "կիրովական", "kirovakan")
DELIVERY_CITY_ERROR = (
    "Առաքումը հասանելի է միայն Վանաձոր քաղաքում։ "
    "Խնդրում ենք նշել Ձեր հասցեում «Վանաձոր»։"
)


class CustomerInfoForm(forms.Form):
    customer_name = forms.CharField(
        label="Անուն",
        max_length=255,
        error_messages={"required": "Խնդրում ենք նշել Ձեր անունը։"},
    )
    phone = forms.CharField(
        label="Հեռախոսահամար",
        max_length=32,
        error_messages={"required": "Խնդրում ենք նշել Ձեր հեռախոսահամարը։"},
    )
    address = forms.CharField(
        label="Հասցե",
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "Օր.՝ Վանաձոր, Տիգրան Մեծի փող. 12"}
        ),
        error_messages={"required": "Խնդրում ենք նշել առաքման հասցեն։"},
    )
    comment = forms.CharField(
        label="Լրացուցիչ տեղեկություն",
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )

    def clean_address(self):
        address = self.cleaned_data["address"]
        if not any(alias in address.lower() for alias in DELIVERY_CITY_ALIASES):
            raise forms.ValidationError(DELIVERY_CITY_ERROR)
        return address
