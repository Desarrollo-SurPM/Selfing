from collections import defaultdict
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from ..models import EmergencyContact


@login_required
def panic_button_view(request):
    contacts_by_company = defaultdict(lambda: defaultdict(list))
    general_contacts = []
    all_contacts = EmergencyContact.objects.select_related('company', 'installation').all()

    for contact in all_contacts:
        if not contact.company and not contact.installation:
            general_contacts.append(contact)
        elif contact.company and not contact.installation:
            contacts_by_company[contact.company.name]['company_contacts'].append(contact)
        elif contact.installation:
            company_name = contact.installation.company.name
            contacts_by_company[company_name][contact.installation.name].append(contact)

    context = {'general_contacts': general_contacts, 'contacts_by_company': dict(contacts_by_company)}
    for company_name in context['contacts_by_company']:
        context['contacts_by_company'][company_name] = dict(context['contacts_by_company'][company_name])

    return render(request, 'operator/panic_button.html', context)
