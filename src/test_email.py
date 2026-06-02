import smtplib
from email.mime.text import MIMEText

smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = "tiny.excellencer@gmail.com"
smtp_pass = "icgkckluwhpxjxxa" 
to_email = "tiny.excellencer@gmail.com"

msg=MIMEText("This is a test email from Python.")
msg["Subject"]="Gmail SMTP Test"
msg["From"]=smtp_user
msg["To"]=to_email

with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(smtp_user, smtp_pass)
    server.send_message(msg)

print("Email sent successfully!")