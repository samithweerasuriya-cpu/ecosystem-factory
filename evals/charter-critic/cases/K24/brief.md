# Problem brief

## 1. Title <!-- field: title -->
Village hall booking desk

## 2. Short name <!-- field: slug -->
village-hall-desk

## 3. Goal <!-- field: goal -->
Groups ask to book the three rooms of the Thornby village hall by e-mail or by a note left at the front desk. When this works, the warden gets every Friday a checked list of the requests, each checked against the calendar with clashes flagged, so every room is used by exactly one group at a time and nobody waits weeks for an answer.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Front Desk (users: type up notes, work through the list and send the replies). Margery Holt (approver: approves the list before anything goes in the calendar). Bookings Treasurer (stakeholders: needs every confirmed booking to raise the invoice). Hall Trustees (stakeholders: want fair use across the village). Booking groups (stakeholders: want a quick, clear answer).

## 5. Current process <!-- field: current_process -->
Steps: the front desk types up notes and prints the e-mails, the warden checks them against the calendar, writes bookings in and the front desk replies. Problems: twice last term the Garden Room was given to two groups at once; notes left at the front desk wait a week before anyone types them. The calendar is a shared spreadsheet that the treasurer also reads to raise invoices, so a wrong booking turns into a wrong invoice.

## 6. Scope <!-- field: scope -->
In: one week's requests by e-mail or note in, and a checked list out. Out: invoices and payments, keys and alarm codes, the annual village show, the playing field.

## 7. Inputs <!-- field: inputs -->
Plain-text requests, one request each: group name, room, date, start and end time, number of people. About 25 a week. Sample: thornby-requests.txt (made up).

## 8. Glossary <!-- field: glossary -->
Great Hall: the main room with the stage, up to 120 people. Garden Room: the room onto the garden, up to 30 people. Snug: the small meeting room, up to 10 people. Clash: two bookings for the same room that overlap in time. Front Desk: the volunteer team at the entrance, not a person. Warden: the trustee who runs bookings, a role that rotates each year. Setting-up time: the half hour before a booking that counts as part of it. Note: a request written on paper and left at the front desk, typed up before it is checked. Room limit: the most people a room may hold, set by the hall's fire certificate.

## 9. Context pack <!-- field: context_inventory -->
thornby-requests.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A table, one row per request: request line, group, room, date, start, end, decision (propose, clash or refuse) and a one-sentence reason. A request with no room or no time is refused as incomplete; a request for more people than the room holds is refused with the room's limit. A request for the playing field is refused as out of scope. A request outside opening hours is refused with the reason.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 no proposed booking overlaps another booking for the same room (blocker). Q02 every row quotes the request it came from (major). Q03 a request outside opening hours (08:00 to 23:00) is refused, with the reason (major). Q04 the reason is one sentence (minor). Q05 a request for more people than the room holds is refused with the room's limit (major). Q06 setting-up time counts as part of the booking when checking clashes (major). Q07 a group's name is copied exactly as it wrote it (minor).

## 14. Examples <!-- field: examples -->
Good: "Mon 2099-11-02 | Snug | Parish walking group | 19:00-20:30 | propose | no clash". Good: "Wed 2099-11-04 | Garden Room | Art class | 10:00-12:00 | clash | Garden Room booked 09:30-11:00 by the baby clinic". Bad: "Wed 2099-11-04 | Garden Room | Art class | 10:00-12:00 | propose", because it overlaps the baby clinic (breaks Q01). Bad: "Sat 2099-11-07 | Great Hall | Barn dance | 20:00-23:45 | propose", because it runs past 23:00 (breaks Q03). Good: "Thu 2099-11-05 | Great Hall | Choral society | 19:30-21:30 | propose | no clash, 60 people fits". Bad: "Tue 2099-11-03 | Garden Room | Yoga | 18:00-19:00 | propose", because the Garden Room is booked until 17:45 and setting-up time starts at 17:30 (breaks Q06). Bad: "Fri 2099-11-06 | Snug | Committee | 19:00-21:00 | 14 people | propose", because the Snug holds 10 (breaks Q05). Good: "Sun 2099-11-08 | Snug | Bridge club | 14:00-16:00 | 8 people | propose | no clash, 8 fits". Good: "Sat 2099-11-07 | Garden Room | Toddler party | 10:00-12:00 | 35 people | refuse | the Garden Room holds 30".

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a week of made-up requests with three clashes, and all three are flagged. I give it a week of made-up requests and look at what comes out. I give it a note with no time on it, and it is refused as incomplete.

## 16. Success metrics <!-- field: success_metrics -->
No double bookings in a year. Every group hears back within 5 days. The warden spends under 20 minutes a week on the list.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong booking can be cancelled, but a group that turns up to a double-booked room has lost its evening.

## 18. Systems <!-- field: systems -->
Reads the requests as text. Writes to the hall's booking calendar.

## 19. Gates <!-- field: gates -->
I approve the list every Friday, directly before anything is written to the calendar.

## 20. Limits <!-- field: caps -->
Lower the token limit to 200,000: we are a small charity and want the running cost kept low. Keep the rest.

## 21. Open questions <!-- field: open_questions -->
Should repeat weekly bookings be checked once a term instead of every week? Owner: hall trustees. Does setting-up time count for the Snug? Owner: hall trustees. Should the barn dance licence hours override the 23:00 closing time? Owner: hall trustees. Can the front desk approve Snug bookings alone when the warden is away? Owner: hall trustees.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
