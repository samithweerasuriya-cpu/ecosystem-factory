# Spec: online room booking (draft v1)

## Summary
Members book Room A or Room B online in one-hour slots; staff see the day's bookings each morning.

## Requirements
- R1: A member signs in with their member number and books a free one-hour slot between 09:00 and 20:00 in Room A or Room B. [F1, F2, F3]
- R2: The member receives a confirmation email instantly. [F2, F6]
- R3: The day's booking list is ready for staff by 08:30. [F5]
- R4: The booking page shows free slots in real time. [F1, F3]

## Data
- Booking: member number, room (A or B), date, start hour. [F1, F2, F3]

## Open questions
- Q1: What happens to members who miss bookings? Open.
- Q2: How far ahead may members book? Open.

## Risks
- If members may book far ahead, popular slots can fill early; the answer to Q2 decides this.
