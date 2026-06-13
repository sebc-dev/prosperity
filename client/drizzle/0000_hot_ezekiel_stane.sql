CREATE TABLE `account_members` (
	`id` text PRIMARY KEY NOT NULL,
	`account_id` text NOT NULL,
	`user_id` text NOT NULL,
	`default_share_ratio` text NOT NULL,
	`joined_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `accounts` (
	`id` text PRIMARY KEY NOT NULL,
	`household_id` text NOT NULL,
	`name` text NOT NULL,
	`type` text NOT NULL,
	`currency` text NOT NULL,
	`owner_id` text,
	`created_at` text NOT NULL,
	`archived_at` text
);
--> statement-breakpoint
CREATE TABLE `budget_contributors` (
	`id` text PRIMARY KEY NOT NULL,
	`budget_id` text NOT NULL,
	`user_id` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `budgets` (
	`id` text PRIMARY KEY NOT NULL,
	`category_id` text NOT NULL,
	`period_kind` text NOT NULL,
	`period_start` text NOT NULL,
	`amount_cents` integer NOT NULL,
	`currency` text NOT NULL,
	`scope` text NOT NULL,
	`created_by` text NOT NULL,
	`created_at` text NOT NULL,
	`archived_at` text,
	`carry_over_remainder` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `categories` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`color` text,
	`icon` text,
	`parent_id` text,
	`created_at` text NOT NULL,
	`archived_at` text
);
--> statement-breakpoint
CREATE TABLE `debts` (
	`id` text PRIMARY KEY NOT NULL,
	`from_user_id` text NOT NULL,
	`to_user_id` text NOT NULL,
	`amount_cents` integer NOT NULL,
	`currency` text NOT NULL,
	`account_id` text,
	`source_transaction_id` text,
	`origin` text NOT NULL,
	`share_ratio` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `settlement_lines` (
	`id` text PRIMARY KEY NOT NULL,
	`settlement_id` text NOT NULL,
	`debt_id` text NOT NULL,
	`amount_cents` integer NOT NULL,
	`currency` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `share_requests` (
	`id` text PRIMARY KEY NOT NULL,
	`source_transaction_id` text,
	`requested_by` text NOT NULL,
	`requested_from` text NOT NULL,
	`ratio` text NOT NULL,
	`short_label` text NOT NULL,
	`created_at` text NOT NULL,
	`revoked_at` text
);
--> statement-breakpoint
CREATE TABLE `splits` (
	`id` text PRIMARY KEY NOT NULL,
	`transaction_id` text NOT NULL,
	`account_id` text NOT NULL,
	`category_id` text,
	`amount_cents` integer NOT NULL,
	`currency` text NOT NULL,
	`savings_goal_id` text,
	`leg_role` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `transactions` (
	`id` text PRIMARY KEY NOT NULL,
	`account_id` text NOT NULL,
	`date` text NOT NULL,
	`state` text NOT NULL,
	`payee` text,
	`description` text,
	`category_id` text,
	`created_by` text NOT NULL,
	`created_at` text NOT NULL,
	`confirmed_at` text,
	`voided_at` text,
	`tags` text NOT NULL,
	`debt_generation_override` text NOT NULL,
	`share_request_id` text
);
--> statement-breakpoint
CREATE TABLE `users_public` (
	`id` text PRIMARY KEY NOT NULL,
	`display_name` text NOT NULL,
	`role` text NOT NULL
);
