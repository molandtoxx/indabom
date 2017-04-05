import csv, export, codecs

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.db import IntegrityError
from django.contrib.auth.decorators import login_required

from json import loads, dumps

from .convert import full_part_number_to_broken_part
from .models import Part, PartClass, Subpart, DistributorPart
from .forms import UploadFileForm
from .octopart_parts_match import match_part

@login_required
def home(request):
    # get all top level assemblies
    parts = Part.objects.all().order_by('number_class__code', 'number_item', 'number_variation')
    return TemplateResponse(request, 'bom/dashboard.html', locals())

@login_required
def indented(request, part_id):
    parts = Part.objects.filter(id=part_id)[0].indented()
    qty = 100
    extended_cost_complete = True
    
    unit_cost = 0
    for item in parts:
        # for each item, get the extended quantity,
        eq = qty * item['quantity']
        item['extended_quantity'] = eq

        # then get the lowest price & distributor at that quantity, 
        p = item['part']
        dps = DistributorPart.objects.filter(part=p)
        disty_price = None
        disty = None
        order_qty = eq
        for dp in dps:
            if dp.minimum_order_quantity < eq and (disty is None or dp.unit_cost < disty_price):
                disty_price = dp.unit_cost
                disty = dp
            elif disty is None:
                disty_price = dp.unit_cost
                disty = dp
                if dp.minimum_order_quantity > eq:
                    order_qty = dp.minimum_order_quantity

        item['distributor_price'] = disty_price
        item['distributor_part'] = disty
        item['order_quantity'] = order_qty
        
        # then extend that price
        item['extended_cost'] = eq * disty_price if disty_price is not None and eq is not None else None

        unit_cost = unit_cost + disty_price * item['quantity'] if disty_price is not None else unit_cost
        if disty is None:
            extended_cost_complete = False

    extended_cost = unit_cost * qty
    
    return TemplateResponse(request, 'bom/indented.html', locals())

@login_required
def export_part_indented(request, part_id):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="indabom_parts_indented.csv"'

    bom = Part.objects.filter(id=part_id)[0].indented()
    qty = 100
    unit_cost = 0
    
    fieldnames = ['level', 'part_number', 'quantity', 'part_description', 'part_revision', 'part_manufacturer', 'part_manufacturer_part_number', 'part_ext_qty', 'part_order_qty', 'part_seller', 'part_cost', 'part_ext_cost']

    writer = csv.DictWriter(response, fieldnames=fieldnames)
    writer.writeheader()
    for item in bom:
        # for each item, get the extended quantity,
        eq = qty * item['quantity']
        item['extended_quantity'] = eq
        # then get the lowest price & distributor at that quantity, 
        p = item['part']
        dps = DistributorPart.objects.filter(part=p)
        disty_price = None
        disty = None
        order_qty = eq
        for dp in dps:
            if dp.minimum_order_quantity < eq and (disty is None or dp.unit_cost < disty_price):
                disty_price = dp.unit_cost
                disty = dp
            elif disty is None:
                disty_price = dp.unit_cost
                disty = dp
                if dp.minimum_order_quantity > eq:
                    order_qty = dp.minimum_order_quantity

        item['distributor_price'] = disty_price
        item['distributor_part'] = disty
        item['order_quantity'] = order_qty
        
        # then extend that price
        item['extended_cost'] = eq * disty_price if disty_price is not None and eq is not None else None

        unit_cost = unit_cost + disty_price * item['quantity'] if disty_price is not None else unit_cost

        row = {
        'level': item['indent_level'], 
        'part_number': item['part'].full_part_number(), 
        'quantity': item['quantity'], 
        'part_description': item['part'].description, 
        'part_revision': item['part'].revision, 
        'part_manufacturer': item['part'].manufacturer, 
        'part_manufacturer_part_number': item['part'].manufacturer_part_number, 
        'part_ext_qty': item['extended_quantity'],
        'part_order_qty': item['order_quantity'],
        'part_seller': item['distributor_part'].distributor.name,
        'part_cost': item['distributor_price'],
        'part_ext_cost': item['extended_cost'],
        }
        writer.writerow(row)
    return response

@login_required
def upload_part_indented(request, part_id):
    response = {
        'errors': [],
        'status': 'ok',
    }

    parts = []
    part = get_object_or_404(Part, id=part_id)
    response['part'] = part.description

    if request.POST and request.FILES:
        csvfile = request.FILES['csv_file']
        dialect = csv.Sniffer().sniff(codecs.EncodedFile(csvfile, "utf-8").read(1024))
        csvfile.open()
        reader = csv.reader(codecs.EncodedFile(csvfile, "utf-8"), delimiter=',', dialect=dialect)
        headers = reader.next()

        Subpart.objects.filter(assembly_part=part).delete()

        for row in reader:
            partData = {}
            for idx, item in enumerate(row):
                partData[headers[idx]] = item
            if 'part_number' in partData and 'quantity' in partData:
                civ = full_part_number_to_broken_part(partData['part_number'])
                subparts = Part.objects.filter(number_class=civ['class'], number_item=civ['item'], number_variation=civ['variation'])
                
                if len(subparts) == 0:
                    response['status'] = 'failed'
                    response['errors'].append('subpart doesn''t exist')
                    return HttpResponse(dumps(response), content_type='application/json')

                subpart = subparts[0]
                count = partData['quantity']

                sp = Subpart(assembly_part=part,assembly_subpart=subpart,count=count)
                sp.save()
    
    response['parts'] = parts

    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/bom/'))

@login_required
def upload_parts(request):
    
    # TODO: Finish this endpoint
    
    response = {
        'errors': [],
        'status': 'ok',
    }
    parts = []

    if request.POST and request.FILES:
        csvfile = request.FILES['csv_file']
        dialect = csv.Sniffer().sniff(codecs.EncodedFile(csvfile, "utf-8").read(1024))
        csvfile.open()
        reader = csv.reader(codecs.EncodedFile(csvfile, "utf-8"), delimiter=',', dialect=dialect)
        headers = reader.next()

        for row in reader:
            partData = {}
            for idx, item in enumerate(row):
                partData[headers[idx]] = item
            parts.append(partData)

    response['parts'] = parts

    return HttpResponse(dumps(response), content_type='application/json')

@login_required
def export_part_list(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="indabom_parts.csv"'

    parts = Part.objects.all().order_by('number_class__code', 'number_item', 'number_variation')

    fieldnames = ['part_number', 'part_description', 'part_revision', 'part_manufacturer', 'part_manufacturer_part_number', 'part_minimum_order_quantity', 'part_minimum_pack_quantity', 'part_unit_cost']

    writer = csv.DictWriter(response, fieldnames=fieldnames)
    writer.writeheader()
    for item in parts:
        row = {
        'part_number': item.full_part_number(), 
        'part_description': item.description, 
        'part_revision': item.revision, 
        'part_manufacturer': item.manufacturer, 
        'part_manufacturer_part_number': item.manufacturer_part_number, 
        'part_minimum_order_quantity': item.minimum_order_quantity, 
        'part_minimum_pack_quantity': item.minimum_pack_quantity,
        'part_unit_cost': item.unit_cost,
        }
        writer.writerow(row)

    return response

@login_required
def octopart_part_match(request, part_id):
    response = {
        'errors': [],
        'status': 'ok',
    }

    parts = Part.objects.filter(id=part_id)

    if len(parts) == 0:
        response['status'] = 'failed'
        response['errors'].append('no parts found with given part_id')
        return HttpResponse(dumps(response), content_type='application/json')

    distributor_parts = match_part(parts[0])
    
    if len(distributor_parts) > 0:
        for dp in distributor_parts:
            try:
                dp.save()
            except IntegrityError:
                continue
    else:
        response['status'] = 'failed'
        response['errors'].append('octopart wasn''t able to find ant parts with given manufacturer_part_number')
        return HttpResponse(dumps(response), content_type='application/json')
        
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/bom/'))

@login_required
def octopart_part_match_indented(request, part_id):
    response = {
        'errors': [],
        'status': 'ok',
    }

    parts = Part.objects.filter(id=part_id)

    if len(parts) == 0:
        response['status'] = 'failed'
        response['errors'].append('no parts found with given part_id')
        return HttpResponse(dumps(response), content_type='application/json')

    subparts = parts[0].subparts.all()

    for part in subparts:
        distributor_parts = match_part(part)
        if len(distributor_parts) > 0:
            for dp in distributor_parts:
                try:
                    dp.save()
                except IntegrityError:
                    continue
        
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/bom/'))
