# Thin problem: answers (T1.1)

Problem: synthetic meeting notes → action-item list; writer + critic (the default thin problem).
Answers recorded verbatim on 2026-10-27, one question at a time. All data is synthetic.

## 1. Outcome

Turn a set of meeting notes into a clean list of action items, so nobody has to re-read the notes to know who does what by when.

## 2. Scope

In scope: one meeting’s notes as plain text in, one action-item list out. Out of scope: calendars, emails, task tools, multiple meetings, and any real names or company data. All inputs are synthetic

## 3. Input

A plain-text file of synthetic meeting notes, 150–400 words, with a date, attendees by first name, and discussion paragraphs

## 4. Output

A Markdown table with one row per action: ID (A1, A2…), action (starts with a verb), owner (an attendee’s name, or ‘unassigned’), due date (from the notes, or ‘not stated’), and source (the sentence the action came from, quoted, at most 25 words).

## 5. Three quality rules

* “Every action is backed by a quoted sentence from the notes; nothing invented. (major)”
* “Owner and due date come only from the notes; if missing, say ‘unassigned’ or ‘not stated’, never guess. (major)”
* “No duplicates and nothing missed: every commitment in the notes appears exactly once. (major)”

## 6. One good and one bad example

* Good: “A1 | Send the revised budget to the team | Priya | Friday 31 Oct | ‘Priya will send the revised budget by Friday.’”
* Bad: “A2 | Book the venue | Tom | next week | (no source)”. The owner and date are guessed, and there’s no quoted sentence. It breaks rules 1 and 2.

## 7. Gate

One human gate before the list is final: Samith approves or rejects the reviewed list. No external writes; the output stays a file.
