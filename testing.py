# Main function of this code is an invoicing system. The written Python code searches
# a SQL database to find all charges for a given project that the client is working on. 

from decimal import *
from prisma import Prisma
import requests
import os
import json
import base64
from reportlab.pdfgen import canvas
from datetime import date, timedelta
from dotenv import load_dotenv


def main() -> None:
    f = open('config.json', encoding="utf-8")
    data = json.load(f)
    db = Prisma()

    try:
        db.connect()
        client_keys = list(data['clients'].keys())
        iterator = iter(client_keys)
        try:
            while iterator:
                exclude = data['Exclude']
                element = data['clients'][next(iterator)]
                email = element['email']
                company = element['company']
                if len(element['productions']) == 0:
                    print(f"{company} does not have any productions")
                    continue

                for production in element['productions']:
                    production_name = production

                    payable_metadata = db.payable_metadata.find_many(
                    where={
                        "transaction": {
                            "production": {
                                "name" : production_name, 
                                "producer_firm": {
                                    "name": company
                                }
                            }
                        }
                    }
                    )
                    invoice_data = db.producer_firm_tax_info.find_first(
                    where={
                        "producer_firm": {
                                "name": company
                            }
                        }
                    )
                    result = db.payable_category.find_many(
                        where={
                                "payable_metadata": {
                                    "transaction": {
                                        "production": {
                                            "name" : production_name, 
                                            "producer_firm": {
                                                "name": company  
                                            }
                                        }
                                    }
                                }
                        },
                        include={"custom_category":True, "payable_metadata":True}
                    )
                    nested_dict = {}
                    vendors = []
                    invoiceTotal = 0
                    for item in result:
                        section_name = item.custom_category.section
                        item_name = item.custom_category.item
                        vendor_name = item.payable_metadata.vendor_name
                        total = item.amount_in_cents
                        vendors.append(vendor_name)
                        if item.payable_metadata.type == 'ESTIMATE':
                            continue
                        if section_name == None:
                            section_name = "Custom"
                        add_data(nested_dict, section_name, item_name, vendor_name, total)

                    create_pdf(payable_metadata, invoice_data, email, invoiceTotal, element, production_name, nested_dict, vendors, exclude, production_name + ' Invoice.pdf')
                rid = input(f"Would you like to delete all productions for {company} from the config file? (y/n)")
                if rid == 'y':
                    delete_productions(element, data)
                    print("All productions deleted \n")
                else:
                    print("No productions were deleted")

        except StopIteration: 
            db.disconnect()
    finally:
        db.disconnect()

def add_data(nested_dict, section_name, item_name, vendor_name, total):
    if section_name in nested_dict:
        section = nested_dict[section_name]
        if item_name in section:
            section[item_name].append((vendor_name, total))
        else:
            section[item_name] = [(vendor_name, total)]
    else:
        nested_dict[section_name] = {item_name: [(vendor_name, total)]}

def delete_productions(element, data):
    element['productions'] = []

    with open('config.json', 'w') as file:
        json.dump(data, file, indent=3)

def create_pdf(payable_metadata, invoice_data, email, invoiceTotal, element, production_name, nested_dict, vendors, exclude, output_file):
    output_folder = "RC-Invoices"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    storage = os.path.join(output_folder, output_file)
    c = canvas.Canvas(storage)

# Page 1
    # Set font properties
    c.setFont("Helvetica", 11)
    c.setStrokeColorRGB(0, 0, 0)  # Blk color
    c.setFillColorRGB(0,0,0) 
    c.setLineWidth(1)  # 1-point widths

    image_path = "RC-Invoice.jpg" 
    c.drawImage(image_path, 60, 740, width=210, height=75)  # Adjust position and size
    c.line(60, 740, 545, 740) #H

    # invoice number generation
    try:
        with open('invoice_number.json', 'r') as file:
            data = json.load(file)
            invoice_number = data['invoice_number']
    except FileNotFoundError:
        invoice_number = 1

    # Increment the invoice number for the next run
    invoice_number = int(invoice_number)
    invoice_number += 1
    invoice_number_padded = str(invoice_number).zfill(5)

    # Save the updated invoice number
    data = {'invoice_number': invoice_number_padded}
    with open('invoice_number.json', 'w') as file:
        json.dump(data, file)

    current_date = date.today()
    formatD = current_date.strftime("%m/%d/%Y")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(475, 775, "Invoice #"+invoice_number_padded) #INVOICE NUMBER CHANGED AND SAVED IN A SEPERATE JSON FILE THAT INCREMENTS AFTER EVERY CALL BY 1 
    c.drawString(488, 762, "Issue Date")
    c.setFont("Helvetica", 10)
    c.drawString(486, 749, str(formatD))

    c.setFont("Helvetica", 25)
    c.drawString(63, 700, "RollCredits")
    c.setFont("Helvetica", 10)
    c.drawString(63, 680, "Thank you for using RollCredits!")

    if invoice_data == None:
        street = "None Provided"
        z = "None Provided"
        city = "None Provided"
        state = "None Provided"
    if invoice_data == None and element['company'] == 'OR':
        street = "3114 NE 36th Ave"
        z = "97212"
        city = "Portland"
        state = "OR"
    if invoice_data != None:
        street = invoice_data.street
        z = invoice_data.zip
        city = invoice_data.city
        state = invoice_data.state

#BILLING INFORMATION SECTION
    c.line(60, 635, 185, 635) #left
    c.setFont("Helvetica-Bold", 10)
    c.drawString(63, 620, "BILL TO")
    c.setFont("Helvetica", 10)
    c.drawString(63, 607, element['company']) # Company Name
    c.drawString(63, 594, email) # email
    c.drawString(63, 581, street) # street  
    c.drawString(63, 568, z + ", " + city + ", " + state) # Zip Code, City, Country

#DETAILS REGARDING PRODUCTION SECTION
    c.line(240, 635, 365, 635) #middle
    c.setFont("Helvetica-Bold", 10)
    c.drawString(243, 620, "PRODUCTION")
    c.setFont("Helvetica", 10)
    c.drawString(243, 607, production_name)

#PAYMENT SECTION
    c.line(420, 635, 545, 635) #right
    c.setFont("Helvetica-Bold", 10)
    c.drawString(423, 620, "PAYMENT DUE")
    future_date = current_date + timedelta(days=30)
    formatted_date = future_date.strftime("%m/%d/%Y")
    c.setFont("Helvetica", 10)
    c.drawString(423, 607, str(formatted_date))  

#TABLE COLUMNS SECTION
    c.line(60, 535, 545, 535)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(63, 515, "ITEM")
    c.drawString(345, 515, "VALUE")
    c.drawString(420, 515, "RATE")
    c.drawString(485, 515, "AMOUNT")
    c.line(60, 504, 545, 504)

#RUNNING THROUGH NUMBER OF TRANSACTIONS, FINDING INVOICES, FINDING TOTAL OF ALL TRANSACTIONS
    total = 0
    excluded_vendors = []
    for metadata in payable_metadata:
        if metadata.type == "ESTIMATE" or (metadata.vendor_name is None and metadata.total_in_cents is None):
            continue
        if metadata.vendor_name is None and metadata.total_in_cents != None:
            total += metadata.total_in_cents
            continue
        if metadata.vendor_name in exclude or "payroll" in metadata.vendor_name or "Payroll" in metadata.vendor_name: # Taking all invoice items and finding the total to take a percentage out later. 
            invoiceTotal += metadata.total_in_cents
            tup = (metadata.vendor_name, metadata.total_in_cents)
            excluded_vendors.append(tup)

        if isinstance(metadata.total_in_cents, int):
            total += metadata.total_in_cents
    realTotal = Decimal(round(total/100, 2))
    realInvoiceTotal = Decimal(round(invoiceTotal/100,2))
    formatted_RealTotal = format(round(realTotal, 2), ",")

#FINDING THE FLAT AMOUNT TO CHARGE BASED ON THE TOTAL
    if element['type'] == 'flat':
        if realTotal < 100000:
            flatRate = Decimal(400.00)
        if realTotal >= 100000 and realTotal < 500000:
            flatRate = Decimal(750.00)
        if realTotal >= 500000 and realTotal < 2000000:
            flatRate = Decimal(2000.00)
        if realTotal > 2000000 and realTotal < 7500000:
            flatRate = Decimal(4000.00)
        if realTotal > 7500000:
            flatRate = Decimal(7500.00)
        formatted_FlatRate = format(round(flatRate, 2), ",")

#FIRST ROW 
        c.setFont("Helvetica", 10)
        c.drawString(63, 485, "Total Transactions")
        c.drawString(315, 485, "$" + formatted_RealTotal) #Total of all transactions
        c.drawString(420, 485, "$" + formatted_FlatRate)# Flat rate amount 
        c.drawString(485, 485, "$" + formatted_FlatRate)# Amount due         

#TAX ROW
        taxPerc = 0 # NISHANT'S INPUT NEEDED HERE
        taxTotal = flatRate * taxPerc
        totalDue = taxTotal + flatRate
        formatted_TotalDue = format(round(totalDue, 2), ",")
        formatted_TaxTotal = format(round(taxTotal, 2), ",")
        c.line(60, 450, 545, 450)
        c.drawString(63, 420, "Subtotal")
        c.drawString(485, 420, "$" + formatted_FlatRate) # Total of Rate (+-) Payroll Invoices (Only for percentage rates)
        c.drawString(63, 395, "Tax")
        c.drawString(485, 395, "$" + formatted_TaxTotal) # Tax amount (Unsure of this currently)

#TOTAL AMOUNT DUE
        c.line(60, 370, 545, 370)
        c.drawString(63, 345, "Total Due")
        c.drawString(485, 345, "$" + formatted_TotalDue) # Subtotal + tax
# Page 2 
        c.showPage()
        c.line(60, 740, 545, 740) #H
        image_path = "/Users/mattlevis/Invoice Docs/RateCard.jpg" 
        c.drawImage(image_path, 50, 525, width=350, height=214)  # Adjust position and size

#RATE SECTION
    if element['type'] == 'percent':
    
#FINDING THE TOTAL BY MULTIPLYING BY THE GIVEN RATE PERCENTAGE
        formatted_TotalRate = format(round(realTotal * Decimal(element['value']), 2), ",")
        formatted_PayrollRate = format(round(realInvoiceTotal * Decimal(element['value']), 2), ",")
        c.setFont("Helvetica", 10)
        c.drawString(63, 485, "Total Transactions")
        c.drawString(315, 485, "$" + formatted_RealTotal) #Total of all transactions
        c.drawString(420, 485, str(100*element['value']) + "%")# rate amount 
        c.drawString(485, 485, "$" + formatted_TotalRate)# Amount due  

#TAKING THE INVOICE TOTAL FROM ABOVE AND MULTIPLYING BY RATE PERCENT
        c.line(60, 460, 545, 460)   
        c.drawString(63, 440, "(less) Payroll Invoices")
        c.drawString(315, 440, "($" + format(round(Decimal(realInvoiceTotal), 2), ",") + ")") # Total of Rate (+-) Payroll Invoices (Only for percentage rates)
        c.drawString(420, 440, str(100*element['value']) + "%")# rate amount 
        c.drawString(485, 440, "$" + formatted_PayrollRate) # Tax amount (Unsure of this currently)

        taxPerc = 0 #UNKNOWN. NEED NISHANT'S INPUT

#TAKING THE TOTAL AND SUBTRACTING THE INVOICE AMOUNT BY IT
        Subtotal = round(Decimal(realTotal * Decimal(element['value'])) - Decimal(realInvoiceTotal * Decimal(element['value'])), 2)
        taxTotal = Subtotal * taxPerc
        totalDue = Decimal(taxTotal + Subtotal)
        formatted_TotalDue = format(round(totalDue, 2), ",")
        formatted_TaxTotal = format(round(taxTotal, 2), ",")
        formatted_Subtotal = format(Subtotal, ",")

#SUBTOTAL AND TAX LINES
        c.line(60, 415, 545, 415)
        c.drawString(63, 385, "Subtotal")
        c.drawString(485, 385, "$" + formatted_Subtotal) # Total of Rate (+-) Payroll Invoices (Only for percentage rates)
        c.drawString(63, 360, "Tax")
        c.drawString(485, 360, "$" + formatted_TaxTotal) # Tax amount (Unsure of this currently)

#TOTAL AMOUNT DUE 
        c.line(60, 335, 545, 335)
        c.drawString(63, 310, "Total Due")
        c.drawString(485, 310, "$" + formatted_TotalDue) # Subtotal + tax


# Page 3 
    c.showPage()
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, 740, "APPENDIX: Summary of Transactions")
    c.setFont("Helvetica-Bold", 22)
    c.setFillColorRGB(1,1,1) 
    c.setLineWidth(30)  

#MAKING THE UNCATEGORIZED SECTION 
    y = 690
    total = 0
    c.line(55, 720, 560, 720)
    c.drawString(60, 713, "Uncategorized")
    c.setFillColorRGB(0,0,0) 
    c.setFont("Helvetica", 11)

#GOING THROUGH THE UNCATEGORIZED TRANSACTIONS 
    for metadata in payable_metadata:
        if metadata.type == 'ESTIMATE' or metadata.vendor_name in vendors or (metadata.vendor_name == None and metadata.total_in_cents == None):
            continue 
# CHECKING IF VENDOR NAME DOES NOT EXIST BUT THERE IS STILL A TRANSACTION ASSOCIATED WITH IT
        if metadata.vendor_name == None and metadata.total_in_cents != None: 
            dollarTotal = round(Decimal(metadata.total_in_cents / 100), 2)
            c.drawString(63, y, "Unknown")
            c.drawString(450, y, '$'+ format(dollarTotal, ","))
            c.setLineWidth(1)  
            c.line(64, y-3, 520, y-3)
            y -= 20
            if y < 60:
                c.showPage()
                y = 690
            total += dollarTotal
            continue
        dollarTotal = round(Decimal(metadata.total_in_cents / 100), 2)
        c.drawString(63, y, metadata.vendor_name)
        c.drawString(450, y, '$'+ format(dollarTotal, ","))
        c.setLineWidth(1)  
        c.line(64, y-3, 520, y-3)
        y -= 20
        if y < 60:
            c.showPage()
            y = 690
        total += dollarTotal
    c.setFont("Helvetica-Bold", 22)
    c.setFillColorRGB(1,1,1) 
    c.drawString(400, 713, '$' + format(total, ","))

#SECTIONS 
    for section_name, section_data in nested_dict.items(): #All section categories 
        c.setFont("Helvetica-Bold", 22)
        c.setFillColorRGB(0,0,0) 
        c.setLineWidth(30)
        total = 0
        for item_data in section_data.values():
            for _, item_total in item_data:
                total += item_total
        total = round(Decimal(total/100), 2)
        c.line(55, y, 560, y)

        y -= 7
        if y < 60:
            c.showPage()
            y = 690
        c.setFillColorRGB(1,1,1) 
        c.drawString(60, y, section_name)
        c.drawString(400, y, '$'+format(total, ","))

        y-=20
        if y < 60:
            c.showPage()
            y = 690
        c.setFillColorRGB(0,0,0) 

#ITEM (SUBSECTION)
        for item_name, item_data in section_data.items(): #All item subcategories 
            y-=15
            if y < 60:
                c.showPage()
                y = 690
            total = 0
            for _, item_total in item_data:
                total += item_total
            total = round(Decimal(total/100), 2)
            c.setFont("Helvetica-Bold", 20)
            c.drawString(400, y, '$'+format(total, ","))
            c.drawString(65, y, item_name)
            y-=20
            if y < 60:
                c.showPage()
                y = 690
            c.setFont("Helvetica", 11)

#ALL TRANSACTIONS UNDER THE ITEM DESCRIPTION 
            for vendor_name, iTotal in item_data: #All vendors and totals 
                iTotal = round(Decimal(iTotal/100), 2)
                total += iTotal
                c.drawString(67, y, vendor_name)
                c.drawString(450, y, '$'+format(iTotal, ","))
                c.setLineWidth(1)  
                c.line(67, y-3, 520, y-3)

                y-=25
                if y < 60:
                    c.showPage()
                    y = 690

    c.setLineWidth(30)  
    c.line(55, y, 560, y)

    y-=7
    if y < 60:
        c.showPage()
        y = 690

    c.setFont("Helvetica-Bold", 22)
    c.setFillColorRGB(1,1,1) 
    c.drawString(60, y, "Excluded Transactions")
    c.drawString(400, y, "$"+format(round(Decimal(realInvoiceTotal), 2), ","))

    y-=30
    if y < 60:
        c.showPage()
        y = 690
    c.setLineWidth(1)  
    c.setFillColorRGB(0,0,0) 
    c.setFont("Helvetica", 11)

    for vend in excluded_vendors:
        vendor, cents = vend
        formatedCents = format(round(Decimal(cents/100),2), ",")
        c.drawString(67, y, vendor)
        c.drawString(450, y, '$'+formatedCents)
        c.line(67, y-3, 520, y-3)
        y-=25
        if y < 60:
            c.showPage()
            y = 690


    c.showPage()
    c.save()

    
    send = input(f"Would you like to send {output_file} via Checkbook to {email}? (y/n)")
    if send == 'y':
        load_dotenv()
        url = os.getenv('URL')
        pdf_file_path = "/Users/mattlevis/FirstIonideProject/RC-Invoices/"+output_file
        sub = "for project " + production_name + " on RollCredits"
        with open(pdf_file_path, "rb") as file:
            encoded_pdf = base64.b64encode(file.read()).decode('utf-8')

        payload = {
            "recipient": email,
            "name": element['company'],
            "amount": round(float(totalDue),2),
            "description": production_name,
            "attachment": encoded_pdf,
            "number":sub
            }
        
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": os.getenv('API_KEY')+":"+os.getenv('API_SECRET')
        }
        response = requests.post(url, json=payload, headers=headers)
        print(response.text) 
        return
    else:
        print(f"{output_file} was not sent\n")
        return
    
    
if __name__ == '__main__':
    main()
