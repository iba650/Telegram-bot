#!/usr/bin/env python3
"""
Generate PDF documentation for Telegram Video Kick Bot commands
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import datetime

def create_bot_commands_pdf():
    """Create a comprehensive PDF guide for all bot commands"""
    
    # Create the PDF document
    doc = SimpleDocTemplate("Telegram_Bot_Commands_Guide.pdf", pagesize=A4,
                          rightMargin=72, leftMargin=72,
                          topMargin=72, bottomMargin=18)
    
    # Container for the 'Flowable' objects
    Story = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=12,
        spaceBefore=12,
        textColor=colors.darkblue
    )
    
    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontSize=14,
        spaceAfter=8,
        spaceBefore=8,
        textColor=colors.darkgreen
    )
    
    # Title
    Story.append(Paragraph("🤖 Telegram Video Kick Bot", title_style))
    Story.append(Paragraph("Complete Command Reference Guide", styles['Heading2']))
    Story.append(Spacer(1, 20))
    
    # Introduction
    intro_text = """
    This bot protects your Telegram group by requiring new members to post a video within a specified time limit. 
    It includes advanced features like anti-spam protection, reward systems, and customizable settings.
    """
    Story.append(Paragraph("📋 Overview", heading_style))
    Story.append(Paragraph(intro_text, styles['Normal']))
    Story.append(Spacer(1, 20))
    
    # Basic Controls Section
    Story.append(Paragraph("📊 Basic Controls", heading_style))
    
    basic_commands = [
        ["/help", "Show all available commands and current settings"],
        ["/status", "Display bot status, statistics, and current configuration"],
        ["/settimer [seconds]", "Change video posting time limit (e.g., /settimer 300 for 5 minutes)"],
        ["/pause", "Temporarily stop the bot from kicking users"],
        ["/resume", "Resume bot operations after being paused"],
    ]
    
    basic_table = Table(basic_commands, colWidths=[2*inch, 4*inch])
    basic_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    Story.append(basic_table)
    Story.append(Spacer(1, 20))
    
    # Protection Features Section
    Story.append(Paragraph("🛡️ Protection Features", heading_style))
    
    protection_commands = [
        ["/antispam", "Toggle anti-spam protection (blocks links, banned words, suspicious users)"],
        ["/interaction", "Toggle interaction mode (timer starts on first message, not on join)"],
        ["/stats", "Show detailed statistics (users kicked, verified, spam blocked)"],
        ["/report", "Generate daily protection report with success rates"],
    ]
    
    protection_table = Table(protection_commands, colWidths=[2*inch, 4*inch])
    protection_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    Story.append(protection_table)
    Story.append(Spacer(1, 20))
    
    # Interactive Features Section
    Story.append(Paragraph("🎉 Interactive Features", heading_style))
    
    interactive_commands = [
        ["/setwelcome [message]", "Set custom welcome message (use {name} for username, {timer} for seconds)"],
        ["/rewards", "Toggle point system for fast video posting (100/50/25 points based on speed)"],
        ["/leaderboard", "Show top 10 users with most points earned"],
        ["/schedule", "Configure active hours for bot operation"],
    ]
    
    interactive_table = Table(interactive_commands, colWidths=[2*inch, 4*inch])
    interactive_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.orange),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightyellow),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    Story.append(interactive_table)
    Story.append(Spacer(1, 20))
    
    # Command Examples Section
    Story.append(Paragraph("💡 Command Examples", heading_style))
    
    examples_text = [
        "<b>Basic Setup:</b>",
        "• /settimer 180 → Set 3-minute timer",
        "• /interaction → Enable interaction mode",
        "• /antispam → Enable spam protection",
        "",
        "<b>Customization:</b>",
        "• /setwelcome Hi {name}! Post a video in {timer}s to stay! → Custom welcome",
        "• /schedule 9 21 → Set active hours from 9 AM to 9 PM",
        "• /rewards → Enable point system for gamification",
        "",
        "<b>Monitoring:</b>",
        "• /status → Quick overview",
        "• /stats → Detailed analytics",
        "• /report → Daily summary report",
        "• /leaderboard → See top contributors"
    ]
    
    for example in examples_text:
        Story.append(Paragraph(example, styles['Normal']))
    
    Story.append(Spacer(1, 20))
    
    # Features Overview Section
    Story.append(Paragraph("⚙️ Feature Overview", heading_style))
    
    features_text = """
    <b>🎯 Core Protection:</b><br/>
    • Automatic user verification through video posting<br/>
    • Configurable time limits (30-600 seconds)<br/>
    • Smart interaction mode (timer starts on first message)<br/><br/>
    
    <b>🛡️ Anti-Spam System:</b><br/>
    • Link detection and blocking<br/>
    • Banned word filtering<br/>
    • Suspicious username detection (crypto/forex bots)<br/>
    • Real-time message monitoring<br/><br/>
    
    <b>🎮 Engagement Features:</b><br/>
    • Point-based reward system<br/>
    • Speed bonuses (faster videos = more points)<br/>
    • User leaderboards<br/>
    • Custom welcome messages<br/><br/>
    
    <b>📊 Analytics & Control:</b><br/>
    • Detailed statistics tracking<br/>
    • Daily protection reports<br/>
    • Scheduled operation mode<br/>
    • Pause/resume functionality<br/>
    """
    
    Story.append(Paragraph(features_text, styles['Normal']))
    Story.append(Spacer(1, 20))
    
    # Admin Requirements Section
    Story.append(Paragraph("👑 Admin Requirements", heading_style))
    
    admin_text = """
    <b>Bot Permissions Required:</b><br/>
    • Delete messages<br/>
    • Ban users<br/>
    • Read message history<br/>
    • Send messages<br/><br/>
    
    <b>Command Access:</b><br/>
    • All configuration commands require admin privileges<br/>
    • Regular users can only trigger the verification process<br/>
    • Bot automatically detects admin status<br/>
    """
    
    Story.append(Paragraph(admin_text, styles['Normal']))
    Story.append(Spacer(1, 20))
    
    # Footer
    Story.append(Paragraph("📅 Generated on: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), styles['Normal']))
    Story.append(Paragraph("🤖 Video Kick Bot - Professional Group Protection", styles['Normal']))
    
    # Build PDF
    doc.build(Story)
    print("✅ PDF generated successfully: Telegram_Bot_Commands_Guide.pdf")

if __name__ == "__main__":
    create_bot_commands_pdf()