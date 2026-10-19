# Decision reports

Native report List and independent full-root Get through the host SDK.

List requires both inclusive offset-free Start Time and Created Time ranges; timezone is unknown. The assigned List whitelist retains business fields and exact native amount strings while excluding operators, account numbers, free text and nested detail. Qualified starting pageSize1000 is not a measured maximum.

Get accepts the native integer id and returns the entire native root. Qualified `--live --with-detail` fetches only the selected window, keeping `record` and `detail` separate. History and other child endpoints remain unqueried; neither Get nor composition saves/imports data. Help lists exact flags and native identity.
