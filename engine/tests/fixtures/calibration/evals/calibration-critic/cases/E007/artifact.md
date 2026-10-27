# Spec: online room booking (draft v1)

## Summary
Online booking of the two meeting rooms by members, with a confirmation email and a morning list for staff.

## Requirements
- R1: Members book Room A (8 seats) or Room B (20 seats). [F1]
- R2: A booking is one hour, starting on the hour between 09:00 and 19:00, so it ends by 20:00. [F3]
- R3: Members identify themselves with their member number; the confirmation goes to the email on file and arrives within 10 minutes. [F2, F6]
- R4: Staff see the day's bookings by 08:30. [F5]

## Data
- Member: member number, email address. [F2]
- Booking: room, date, start hour, member number. [F1, F3]

## Open questions
- Q1: What happens to members who miss bookings? Open.
- Q2: How far ahead may members book? Open.

## Risks
- Missed bookings may block rooms until Q1 is answered.
