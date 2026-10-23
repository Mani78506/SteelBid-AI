#!/usr/bin/env python3
"""
Generate SteelBid AI Demo Script PDF
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Create PDF
output_path = "SteelBid_AI_Demo_Script.pdf"
doc = SimpleDocTemplate(
    output_path,
    pagesize=A4,
    rightMargin=0.75*inch,
    leftMargin=0.75*inch,
    topMargin=0.75*inch,
    bottomMargin=0.75*inch
)

# Styles
styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle(
    'CustomTitle',
    parent=styles['Heading1'],
    fontSize=24,
    textColor=colors.HexColor('#1e3a5f'),
    spaceAfter=30,
    alignment=TA_CENTER,
    fontName='Helvetica-Bold'
)

subtitle_style = ParagraphStyle(
    'CustomSubtitle',
    parent=styles['Heading2'],
    fontSize=16,
    textColor=colors.HexColor('#2f6fde'),
    spaceAfter=20,
    fontName='Helvetica-Bold'
)

heading_style = ParagraphStyle(
    'CustomHeading',
    parent=styles['Heading3'],
    fontSize=14,
    textColor=colors.HexColor('#1e3a5f'),
    spaceAfter=12,
    spaceBefore=20,
    fontName='Helvetica-Bold'
)

body_style = ParagraphStyle(
    'CustomBody',
    parent=styles['Normal'],
    fontSize=11,
    textColor=colors.black,
    spaceAfter=10,
    leading=14,
    fontName='Helvetica'
)

bullet_style = ParagraphStyle(
    'CustomBullet',
    parent=styles['Normal'],
    fontSize=11,
    textColor=colors.black,
    spaceAfter=8,
    leftIndent=20,
    leading=14,
    fontName='Helvetica'
)

url_style = ParagraphStyle(
    'CustomURL',
    parent=styles['Normal'],
    fontSize=10,
    textColor=colors.HexColor('#2f6fde'),
    spaceAfter=5,
    fontName='Helvetica-Oblique'
)

# Content
story = []

# Title Page
story.append(Paragraph("SteelBid AI", title_style))
story.append(Paragraph("Product Demo Script", subtitle_style))
story.append(Paragraph("2-3 Minute Walkthrough", subtitle_style))
story.append(Spacer(1, 0.5*inch))

story.append(Paragraph("<b>Application URL:</b>", body_style))
story.append(Paragraph("https://web-production-972cd.up.railway.app", url_style))
story.append(Spacer(1, 0.2*inch))

story.append(Paragraph("<b>Demo Account:</b>", body_style))
story.append(Paragraph("Email: admin@apex.demo", body_style))
story.append(Paragraph("Password: SteelBid#Demo2026", body_style))
story.append(Spacer(1, 0.5*inch))

story.append(Paragraph("A connected, production-ready Steel Business Operating System", body_style))
story.append(Paragraph("for traders, distributors, fabricators, and contractors.", body_style))
story.append(PageBreak())

# Overview Table
story.append(Paragraph("Demo Overview", heading_style))

overview_data = [
    ['Time', 'Scene', 'Action', 'Voiceover/Notes'],
    ['0:00-0:15', 'Login', 'Show premium login screen', 'SteelBid AI — the Steel Business Operating System'],
    ['0:15-0:35', 'Command Center', 'Navigate to dashboard', 'Real-time KPIs: inventory, sales, receivables'],
    ['0:35-0:50', 'Inventory', 'Click Inventory tab', 'Stock lots, heat numbers, quality states — full traceability'],
    ['0:50-1:05', 'Materials', 'Click Materials tab', 'Organization-specific catalog with grades and standards'],
    ['1:05-1:20', 'Inquiries → Quotations', 'Click Inquiries, then Quotations', 'Customer inquiries with availability → quotations with margin calculations'],
    ['1:20-1:35', 'Sales Orders', 'Click Sales Orders', 'Lot allocation, shortage analysis, real-time stock reservation'],
    ['1:35-1:50', 'Procurement', 'Click Procurement', 'Supplier comparison, landed cost, purchase orders'],
    ['1:50-2:05', 'Market Intelligence', 'Click Market', 'Price observations, market trends (synthetic demo structure)'],
    ['2:05-2:20', 'Fabrication', 'Click Fabrication', 'BOMs, work orders, inspections for fabricators'],
    ['2:20-2:35', 'Tenders', 'Click Tenders', 'Document extraction, BOQ review for contractors'],
    ['2:35-2:50', 'Projects & Logistics', 'Click Projects, then Logistics', 'Project tracking, dispatch planning, vehicle management'],
    ['2:50-3:00', 'Finance & AI Briefing', 'Click Finance, then AI Briefing', 'Receivables, payables, inventory valuation — AI-powered insights'],
    ['3:00-3:10', 'Logout', 'User menu → Logout', 'Secure session handling. SteelBid AI — connected, production-ready.']
]

overview_table = Table(overview_data, colWidths=[0.8*inch, 1.2*inch, 1.8*inch, 2.2*inch])
overview_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 9),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ('FONTSIZE', (0, 1), (-1, -1), 8),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')])
]))
story.append(overview_table)
story.append(Spacer(1, 0.3*inch))
story.append(PageBreak())

# Detailed Steps
story.append(Paragraph("Preparation", heading_style))
story.append(Paragraph("• Open browser to https://web-production-972cd.up.railway.app", bullet_style))
story.append(Paragraph("• Start screen recording (OBS, Loom, or built-in recorder)", bullet_style))
story.append(Paragraph("• Set browser to full screen (F11) for professional look", bullet_style))
story.append(Spacer(1, 0.2*inch))

story.append(Paragraph("Step 1: Login Screen (0:00-0:15)", heading_style))
story.append(Paragraph("1. Browser loads to login page automatically", bullet_style))
story.append(Paragraph("2. Pause for 2-3 seconds to show premium industrial design", bullet_style))
story.append(Paragraph("3. Type: admin@apex.demo", bullet_style))
story.append(Paragraph("4. Type: SteelBid#Demo2026", bullet_style))
story.append(Paragraph("5. Click 'Sign in' button", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'SteelBid AI — the Steel Business Operating System for traders, distributors, fabricators, and contractors. Let's log in.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 2: Steel Business Command Center (0:15-0:35)", heading_style))
story.append(Paragraph("1. Wait for dashboard to load fully", bullet_style))
story.append(Paragraph("2. Hover over KPI cards (Inventory Valuation, Open Sales Orders, Purchase Commitments, Overdue Receivables)", bullet_style))
story.append(Paragraph("3. Scroll down to 'Recent Inquiries' and 'Market Intelligence' sections", bullet_style))
story.append(Paragraph("4. Pause to show live data (~₹11.4M inventory, ~₹1.3M sales orders)", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'The Command Center gives you a real-time view of your entire steel business. Inventory valuation, open sales orders, purchase commitments, and overdue receivables — all in one place. Recent inquiries and market intelligence keep you informed.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 3: Inventory Module (0:35-0:50)", heading_style))
story.append(Paragraph("1. Click 'Inventory' in left sidebar", bullet_style))
story.append(Paragraph("2. Scroll through stock lots table", bullet_style))
story.append(Paragraph("3. Point out columns: Material, Warehouse, Lot/Heat Number, On-hand, Available, Quality State", bullet_style))
story.append(Paragraph("4. Highlight example: ISMB-200 with 55 MT on-hand, 40 MT available, 15 MT quarantined", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Inventory management with full traceability. Track stock lots by warehouse, heat numbers, and quality states. See on-hand, reserved, and available quantities at a glance. Quality states like OK, Quarantined, and Rejected ensure material compliance.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 4: Materials Catalog (0:50-1:05)", heading_style))
story.append(Paragraph("1. Click 'Materials' in sidebar", bullet_style))
story.append(Paragraph("2. Show catalog with Form, Grade, Standard, Weight/MT columns", bullet_style))
story.append(Paragraph("3. Scroll to see variety: ISMB, Plates, Coils, Angles, Channels", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Your organization-specific materials catalog. Define forms, grades, and standards that match your product range. From structural sections to plates and coils — everything standardized.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 5: Inquiries → Quotations (1:05-1:20)", heading_style))
story.append(Paragraph("1. Click 'Inquiries' in sidebar", bullet_style))
story.append(Paragraph("2. Show inquiry list with customer, status, items", bullet_style))
story.append(Paragraph("3. Click 'Quotations' in sidebar", bullet_style))
story.append(Paragraph("4. Highlight quotation example: QTN-2026-0005 with 100 MT, cost ₹5.62M, selling ₹6.39M, 12% margin", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Capture customer inquiries with real-time stock availability. Convert to quotations with cost versus selling price, margin calculations, and version tracking. This quotation shows 100 MT at a 12% margin.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 6: Sales Orders (1:20-1:35)", heading_style))
story.append(Paragraph("1. Click 'Sales Orders' in sidebar", bullet_style))
story.append(Paragraph("2. Show SO list with customer, value, status", bullet_style))
story.append(Paragraph("3. Scroll to see allocation and shortage analysis columns", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Convert quotations to sales orders with automatic lot allocation. Shortage analysis tells you exactly what you need to procure. No more manual spreadsheets.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 7: Procurement (1:35-1:50)", heading_style))
story.append(Paragraph("1. Click 'Procurement' in sidebar", bullet_style))
story.append(Paragraph("2. Click 'Suppliers' submenu", bullet_style))
story.append(Paragraph("3. Show supplier list with lead time, rating", bullet_style))
story.append(Paragraph("4. Click 'Purchase Requests' to see pending procurement needs", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Procurement starts with supplier comparison. Compare landed costs, lead times, and ratings. Purchase requests are generated automatically from sales order shortages.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 8: Market Intelligence (1:50-2:05)", heading_style))
story.append(Paragraph("1. Click 'Market' in sidebar", bullet_style))
story.append(Paragraph("2. Show price observations by form, grade, region", bullet_style))
story.append(Paragraph("3. Note: Data is synthetic for demo — real price feed integrates via provider adapter", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Market intelligence keeps you competitive. Track price observations by form, grade, and region. The demo shows synthetic data, but production can connect to licensed price feeds.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(PageBreak())

story.append(Paragraph("Step 9: Fabrication (2:05-2:20)", heading_style))
story.append(Paragraph("1. Click 'Fabrication' in sidebar", bullet_style))
story.append(Paragraph("2. Click 'BOMs' submenu to show Bill of Materials", bullet_style))
story.append(Paragraph("3. Click 'Work Orders' to see production jobs", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'For fabricators, manage BOMs and work orders. Track material consumption, inspections, and allocation. Perfect for production teams.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 10: Tenders (2:20-2:35)", heading_style))
story.append(Paragraph("1. Click 'Tenders' in sidebar", bullet_style))
story.append(Paragraph("2. Show tender list with reference, organization, status", bullet_style))
story.append(Paragraph("3. Mention extraction workflow (PDF/Excel parsing, BOQ review)", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Contractors use the Tenders module. Upload tender documents, extract BOQ items automatically, and review them for estimation. Supports PDF and Excel parsing.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 11: Projects & Logistics (2:35-2:50)", heading_style))
story.append(Paragraph("1. Click 'Projects' in sidebar", bullet_style))
story.append(Paragraph("2. Show project list with type, estimated value", bullet_style))
story.append(Paragraph("3. Click 'Logistics' in sidebar", bullet_style))
story.append(Paragraph("4. Show dispatch planning with warehouse, vehicle, transporter", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Track projects by type — railway, infrastructure, industrial. Logistics handles dispatch planning with vehicle and transporter tracking. Full visibility from warehouse to customer site.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 12: Finance & AI Briefing (2:50-3:00)", heading_style))
story.append(Paragraph("1. Click 'Finance' in sidebar", bullet_style))
story.append(Paragraph("2. Show Receivables, Payables, Valuation tabs", bullet_style))
story.append(Paragraph("3. Click 'AI Briefing' in sidebar", bullet_style))
story.append(Paragraph("4. Show AI-powered shortage analysis and supplier recommendations", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Finance gives you receivables, payables, and inventory valuation. The AI Briefing module provides shortage analysis, supplier recommendations, and price explanations — grounded in your actual data.'</i>", body_style))
story.append(Spacer(1, 0.3*inch))

story.append(Paragraph("Step 13: Logout (3:00-3:10)", heading_style))
story.append(Paragraph("1. Click user menu (top-right, initials or avatar)", bullet_style))
story.append(Paragraph("2. Click 'Logout'", bullet_style))
story.append(Paragraph("3. Return to login screen", bullet_style))
story.append(Paragraph("4. Stop recording", bullet_style))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph("<i>Narration: 'Secure session handling. SteelBid AI — a connected, production-ready Steel Business Operating System.'</i>", body_style))
story.append(Spacer(1, 0.5*inch))
story.append(PageBreak())

# Feature Summary
story.append(Paragraph("Feature Summary", heading_style))

feature_data = [
    ['Module', 'Key Capabilities'],
    ['Command Center', 'Real-time KPIs, recent inquiries, market intel'],
    ['Inventory', 'Stock lots, heat numbers, quality states, reservations'],
    ['Materials', 'Organization catalog, forms, grades, standards'],
    ['Customers', 'CRM, credit terms, GSTIN, contact management'],
    ['Inquiries', 'Customer requests with stock availability'],
    ['Quotations', 'Cost vs selling, margin calculations, version tracking'],
    ['Sales Orders', 'Lot allocation, shortage analysis, reservation'],
    ['Procurement', 'Supplier comparison, landed cost, purchase orders'],
    ['Market', 'Price observations (demo: synthetic, prod: licensed feed)'],
    ['Fabrication', 'BOMs, work orders, inspections, consumption'],
    ['Tenders', 'Document extraction, BOQ review, estimation'],
    ['Projects', 'Project tracking, type classification, value estimates'],
    ['Logistics', 'Dispatch planning, vehicle/transporter tracking'],
    ['Finance', 'Receivables, payables, inventory valuation'],
    ['AI Briefing', 'Shortage analysis, supplier recommendations, explanations']
]

feature_table = Table(feature_data, colWidths=[1.5*inch, 4.5*inch])
feature_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 10),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ('FONTSIZE', (0, 1), (-1, -1), 9),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')])
]))
story.append(feature_table)
story.append(Spacer(1, 0.3*inch))
story.append(PageBreak())

# Demo Credentials
story.append(Paragraph("Demo Credentials", heading_style))

cred_data = [
    ['Role', 'Login', 'Password', 'Organization'],
    ['Admin (all orgs)', 'admin@railbuild.demo', 'SteelBid#Demo2026', 'All 4 demo companies'],
    ['Trader admin', 'admin@apex.demo', 'SteelBid#Demo2026', 'Apex Steel Traders'],
    ['Distributor admin', 'admin@metro.demo', 'SteelBid#Demo2026', 'Metro Steel Distributors'],
    ['Fabricator admin', 'admin@precision.demo', 'SteelBid#Demo2026', 'PrecisionSteel Fabricators']
]

cred_table = Table(cred_data, colWidths=[1.5*inch, 2*inch, 1.8*inch, 1.2*inch])
cred_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 9),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ('FONTSIZE', (0, 1), (-1, -1), 9),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')])
]))
story.append(cred_table)
story.append(Spacer(1, 0.5*inch))

# Tips
story.append(Paragraph("Recording Tips", heading_style))
story.append(Paragraph("• Use admin@apex.demo for the main demo — it's a single-org trader, simpler to follow", bullet_style))
story.append(Paragraph("• Wait for full page loads before navigating (no spinning loaders in frame)", bullet_style))
story.append(Paragraph("• Smooth scrolling — use touchpad or scroll wheel, avoid jerky movements", bullet_style))
story.append(Paragraph("• Highlight key data — mouse hover on important numbers (KPIs, margins)", bullet_style))
story.append(Paragraph("• Pause 2-3 seconds on each screen for viewer to absorb", bullet_style))
story.append(Paragraph("• Full-screen browser (F11) for clean, professional look", bullet_style))
story.append(Paragraph("• Good microphone — clear voiceover adds credibility", bullet_style))
story.append(Paragraph("• Background music optional — keep it subtle if used", bullet_style))
story.append(Spacer(1, 0.5*inch))

# Footer
story.append(Paragraph("─" * 60, body_style))
story.append(Paragraph("SteelBid AI — Connected, Production-Ready Steel Business OS", body_style))
story.append(Paragraph("https://web-production-972cd.up.railway.app", url_style))

# Build PDF
doc.build(story)

print(f"✓ PDF generated: {output_path}")
print(f"✓ Location: {os.path.abspath(output_path)}")
