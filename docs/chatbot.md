# Local farmer chatbot

Open `/chatbot/` or select **Farmer assistant** in the application. The chatbot runs inside Django using the project's bilingual agriculture library and local conversation rules. It needs no API key, paid credits, model download, Ollama, or external AI service. Existing OpenAI settings do not enable remote requests.

The response engine works without internet access. Other parts of AgriTwin still need internet to retrieve new NASA data or load external maps. Optional reference links open external websites only when the farmer chooses to follow them.

## Asking questions

The assistant follows the selected Bangla or English interface language and recognizes common Bangla, English, and Banglish farming phrases. It covers crops, irrigation, soil testing, fertilizer planning, pests and symptoms, sowing, drainage, compost, storage, crop rotations, NASA climate information, and using AgriTwin.

It uses recent messages in the current conversation to understand a crop or topic follow-up. For example, ask `How do I irrigate rice?`, then `More details please`. Starting a new conversation gives the assistant a fresh history. Useful Bangla questions include `ধানের জমিতে সেচ কীভাবে দেব?`, `পাতা হলুদ হয়ে যাচ্ছে`, and `মাটি পরীক্ষা কোথায় করব?`. Describe the crop and problem clearly when asking a new question.

This is a local information assistant, not a general language model. It selects guidance and asks for missing details using the information shipped with the application. It can acknowledge greetings and thanks, explain its topics, and help narrow a farming question. An unsupported question gets a clear explanation and examples of supported questions. It cannot answer every general-knowledge question.

The assistant does not fetch live weather, market prices, or new sources. It cannot confirm whether it will rain today or supply today's crop price. It explains what information to check and links to the relevant reference. It does not invent current measurements, diagnose a plant disease from text, or claim that a planning score guarantees yield or profit.

The reference library includes the [Agriculture Information Service](https://ais.gov.bd/), [BAMIS agricultural advisories](https://www.bamis.gov.bd/en/), [Bangladesh Meteorological Department agrometeorology](https://www.bmd.gov.bd/web/bn/agromet_page/), and [NASA POWER climatology documentation](https://power.larc.nasa.gov/docs/services/api/temporal/climatology/). Reference links provide further reading; the chatbot has not retrieved those pages during the conversation. For field diagnosis or a specific treatment plan, contact a local agricultural officer. The agricultural call center number is **16123**.

## Saved farm information

Using saved farm information is **off by default**. Select a farm and the checkbox when sending a question to let the local assistant use that farm's details. Selecting a farm alone does not authorize using its context. Only farms owned by the current browser session are selectable.

The context includes a general district, crop names, area, known soil information, irrigation access, farming priority, and an existing validated NASA climate summary and rotation comparison. It excludes the farm's name, browser session identifier, exact coordinates, budget, and raw NASA response. Arbitrary custom location text is replaced with a general Bangladesh location.

The chatbot never makes a NASA request. When a validated saved analysis exists, it can explain its historical climate values and period without changing the source data. A farm without a valid analysis gets no invented climate measurements. NASA POWER climatology is a regional historical average, not today's weather, a forecast, a soil pH test, or a nitrogen/phosphorus/potassium measurement. Farmer-entered soil pH is identified separately.

Messages and farm summaries are processed by the Django application and are not sent to an AI provider. The farmer's own message may contain personal information, so avoid entering secrets or details that should not be stored.

## Conversation history and privacy

Chat messages are stored in the Django database. Viewing, sending to, and deleting a conversation require its owning browser session. This version has no farmer accounts or cross-device recovery. Keep the browser's session cookie to return to a conversation; anyone using that browser session can access its history. Authorized database or Django admin access is separate from browser-session access.

Use **Clear chat** to delete that conversation and its messages from the application's database. This does not remove copies in database backups. Clearing requires a POST request with CSRF protection. Unchecking the farm context option does not remove previously saved messages; clear the conversation when that history should be deleted.

The page supports normal HTML form submission without JavaScript. JavaScript adds immediate replies and quick questions. Replies are rendered as escaped plain text, and reference links are restricted to the application's reviewed sources.

## Limits

Each question has a 2,000-character limit. A conversation holds at most 80 user and assistant messages; start a new conversation when it fills. The assistant receives a bounded recent history rather than the entire database. Sending is limited to 12 questions per minute per browser session. Invalid or throttled requests do not create messages.

The default local-memory Django cache is suitable for the local prototype. Configure a shared cache before running multiple worker processes so the throttle remains consistent. Keep production HTTPS, cookie, host, and CSRF settings configured when deploying.

## Run and verify

No chatbot-specific environment settings or installation steps are required. From the project root:

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py check_chatbot
.venv\Scripts\python.exe manage.py runserver
```

Open `/chatbot/`, ask a crop question, add a follow-up, and switch the interface language. To test stored farm explanations, explicitly attach an owned farm with an existing NASA analysis. A different browser session must not be able to access the first session's conversations.

Automated local checks do not need external connectivity:

```powershell
.venv\Scripts\python.exe manage.py test chatbot tests.test_chatbot_flow
.venv\Scripts\python.exe manage.py check
```
