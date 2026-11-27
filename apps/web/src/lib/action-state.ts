export type ActionState<TData, TFieldErrors = Record<string, string>> =
	| {
			status: "idle";
	  }
	| {
			status: "success";
			data: TData;
			message?: string;
	  }
	| {
			status: "error";
			fieldErrors?: TFieldErrors;
			message: string;
	  };
